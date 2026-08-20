"""Drives a headless browser through the steps that lead to the booking page."""

from __future__ import annotations

from playwright.async_api import async_playwright

# Booking sites are frequently slow: the reference site used to build this tool
# takes anywhere from 3 to 40 seconds for its first response. These defaults are
# deliberately generous; a timeout here means a missed slot.
NAV_TIMEOUT = 120_000
STEP_TIMEOUT = 60_000


class FlowError(Exception):
    """A step could not be completed."""


class Flow:
    def __init__(self, config, log, debug_dir=None):
        self.config = config
        self.log = log
        self.debug_dir = debug_dir

    async def fetch_text(self):
        """Run every configured step and return the final page's visible text."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            page.set_default_timeout(STEP_TIMEOUT)
            try:
                # "commit" returns as soon as the first byte of the response
                # arrives. Waiting for "domcontentloaded" can take far longer on
                # slow sites, for no benefit: the steps below wait for the exact
                # elements they need anyway.
                await page.goto(self.config.url, wait_until="commit", timeout=NAV_TIMEOUT)

                for index, step in enumerate(self.config.steps, start=1):
                    try:
                        await self._run(page, step)
                    except Exception as exc:
                        if step.optional:
                            self.log(f"  step {index} ({step.describe()}) skipped: optional")
                            continue
                        raise FlowError(
                            f"step {index} failed — {step.describe()}\n"
                            f"  {str(exc).splitlines()[0]}"
                        ) from exc

                await page.wait_for_load_state("load", timeout=NAV_TIMEOUT)
                return await page.inner_text("body")
            except Exception:
                await self._dump(page)
                raise
            finally:
                await browser.close()

    async def _run(self, page, step):
        action = step.action
        timeout = step.timeout or STEP_TIMEOUT

        if action == "goto":
            await page.goto(step.url, wait_until="commit", timeout=NAV_TIMEOUT)
            return

        if action == "wait":
            await page.locator(step.selector).first.wait_for(state=step.state, timeout=timeout)
            return

        if action == "fill":
            target = page.locator(step.selector).first
            await target.wait_for(state="visible", timeout=timeout)
            await target.fill(step.value)
            return

        if action == "select":
            await page.select_option(step.selector, step.value, timeout=timeout)
            return

        if action == "press":
            await page.press(step.selector, step.key, timeout=timeout)
            return

        if action == "check":
            # Styled checkboxes are often visually hidden, with only their
            # <label> clickable, so a plain check() would time out waiting for
            # visibility. Clicking the label first is the reliable path.
            box = page.locator(step.selector).first
            label = page.locator(f"label[for='{step.selector.lstrip('#')}']")
            try:
                if await label.count():
                    await label.first.click(timeout=timeout)
                else:
                    await box.check(timeout=timeout)
            except Exception:
                await box.check(force=True, timeout=timeout)
            return

        if action in {"click", "click_in"}:
            if action == "click_in":
                container = page.locator(step.container).filter(has_text=step.contains)
                count = await container.count()
                if count == 0:
                    raise FlowError(f"no {step.container} containing {step.contains!r}")
                if count > 1:
                    self.log(f"  note: {count} matches for {step.contains!r}, using the first")
                target = container.first.locator(step.selector).first
            else:
                target = page.locator(step.selector).first

            await target.wait_for(state="attached", timeout=timeout)
            if step.navigates:
                async with page.expect_navigation(wait_until="commit", timeout=NAV_TIMEOUT):
                    await target.click(force=step.force, timeout=timeout)
                await page.wait_for_load_state("load", timeout=NAV_TIMEOUT)
            else:
                await target.click(force=step.force, timeout=timeout)
            return

        raise FlowError(f"unsupported action {action!r}")

    async def _dump(self, page):
        """Save the page on failure so the user can fix their selectors."""
        if not self.debug_dir:
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(self.debug_dir / "error.png"), full_page=True)
            (self.debug_dir / "error.html").write_text(await page.content())
            (self.debug_dir / "error.txt").write_text(await page.inner_text("body"))
            self.log(f"  page saved to {self.debug_dir}/ (error.png, error.html, error.txt)")
        except Exception:
            pass
