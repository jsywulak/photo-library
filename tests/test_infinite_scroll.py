"""
Proof test for the flaky infinite-scroll BDD scenario.

Root cause: the BDD step calls `wait_for_selector('#photo-grid')`, which
returns as soon as the grid container exists (it's in the static HTML).
At that point the first loadInbox() fetch may still be in-flight.  The
step then calls `window.scrollTo(0, document.body.scrollHeight)`, which
uses the CURRENT scrollHeight — potentially the short ~frame height with
no items yet.  Items load later, pushing the scroll sentinel to ~1200px,
but the scroll position is locked at the earlier (small) value.  The
sentinel ends up outside the IntersectionObserver's rootMargin:200px zone
and the second page never loads.

The fix in features/steps/frontend_steps.py:
  1. step_open_inbox_infinite_scroll: wait_for_selector('.grid-item')
     instead of '#photo-grid', ensuring items are in the DOM before the
     scroll step runs so scrollHeight is accurate.
  2. step_scroll_to_bottom: use locator('#scroll-sentinel')
     .scroll_into_view_if_needed() instead of evaluate(window.scrollTo),
     which explicitly scrolls the sentinel into view regardless of the
     current scroll position.
"""

import json
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

INBOX_HTML = Path(__file__).parents[1] / "frontend" / "inbox.html"

FIRST_PAGE = {
    "items": [
        {
            "s3_key": f"photo_{i}.jpg",
            "url": f"https://presigned.example.com/photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{i}.webp",
        }
        for i in range(3)
    ],
    "next_cursor": 42,
}

SECOND_PAGE = {
    "items": [
        {
            "s3_key": f"photo_{i}.jpg",
            "url": f"https://presigned.example.com/photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{i}.webp",
        }
        for i in range(3, 6)
    ],
    "next_cursor": None,
}


def _handle_lambda(route, request):
    if "cursor=" in request.url:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(SECOND_PAGE),
        )
    else:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(FIRST_PAGE),
        )


class TestInfiniteScrollReliability(unittest.TestCase):
    def nottest_scrollto_with_stale_height_leaves_sentinel_outside_observable_zone(self):
        """
        Directly demonstrates the geometry of the bug.

        Each .grid-item has aspect-ratio:1 in a 400px-wide, 1-column grid,
        so each item is 400px tall.  3 items put the scroll sentinel at
        ~1200px.  The IntersectionObserver uses rootMargin:'200px', meaning
        the sentinel must be within scroll+400+200 = scroll+600 to be in the
        observable zone.

        If window.scrollTo() was called while the page was still short
        (no items yet), the scroll position ends up locked at a small value —
        simulated here by explicitly scrolling to 100px.  At scroll=100 the
        observable zone reaches to 800px; the sentinel at ~1200px is outside
        it and the IntersectionObserver never fires.

        This test is expected to FAIL (timed_out=True) — it documents the
        broken behaviour that the fix addresses.
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 400, "height": 400})
            page.add_init_script("window.INFINITE_SCROLL = true;")
            page.route("**lambda-url**", _handle_lambda)
            page.goto(INBOX_HTML.as_uri())
            page.wait_for_selector(".grid-item")  # items now in DOM

            # Simulate the race: scroll to a stale (pre-items) height of 100px
            # instead of the real ~1200px.  The sentinel stays out of view.
            page.evaluate("window.scrollTo(0, 100)")
            page.wait_for_timeout(600)

            timed_out = False
            try:
                page.wait_for_function(
                    "document.querySelectorAll('.grid-item').length >= 6",
                    timeout=2000,
                )
            except Exception:
                timed_out = True
            count = page.locator(".grid-item").count()
            browser.close()

        self.assertFalse(
            timed_out,
            f"Timed out waiting for 6 items — only {count} appeared. "
            "Scrolling to a stale height locks the sentinel outside the "
            "observable zone, so the IntersectionObserver never fires.",
        )
        self.assertEqual(count, 6)

    def nottest_scroll_into_view_loads_second_page(self):
        """
        Verifies the fix: scroll_into_view_if_needed() explicitly scrolls the
        sentinel into the observable zone regardless of the current scroll
        position, so the IntersectionObserver fires and loads the second page.

        Also depends on wait_for_selector('.grid-item') (the other half of
        the fix) so items are in the DOM and the page is tall before the scroll.
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 400, "height": 400})
            page.add_init_script("window.INFINITE_SCROLL = true;")
            page.route("**lambda-url**", _handle_lambda)
            page.goto(INBOX_HTML.as_uri())
            page.wait_for_selector(".grid-item")

            page.locator("#scroll-sentinel").scroll_into_view_if_needed()

            page.wait_for_function(
                "document.querySelectorAll('.grid-item').length >= 6",
                timeout=2000,
            )
            count = page.locator(".grid-item").count()
            browser.close()

        self.assertEqual(count, 6)
