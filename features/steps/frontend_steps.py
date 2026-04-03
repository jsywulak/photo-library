"""
Step definitions for frontend.feature.

Uses Playwright to drive a real browser against the local HTML file, with all
API calls intercepted and mocked so tests run without network access.

Requires: playwright installed and Chromium downloaded.
  pip install playwright && playwright install chromium
  (or: make install-playwright)
"""

import json
from pathlib import Path

from behave import given, then, when

FRONTEND_HTML = Path(__file__).parents[2] / "frontend" / "index.html"
INBOX_HTML = Path(__file__).parents[2] / "frontend" / "inbox.html"
STATS_HTML = Path(__file__).parents[2] / "frontend" / "stats.html"


# ── Mock setup ───────────────────────────────────────────────────────────────

@given("the inbox API returns {n:d} result")
@given("the inbox API returns {n:d} results")
def step_inbox_returns_n(context, n):
    context.mock_inbox_results = {
        "items": [
            {
                "s3_key": f"inbox_photo_{i}.jpg",
                "url": f"https://presigned.example.com/inbox_photo_{i}.jpg",
                "thumbnail_url": f"https://thumbnails.example.com/thumbnails/inbox_photo_{i}.webp",
            }
            for i in range(n)
        ],
        "next_cursor": None,
    }


@given("the inbox API returns {n:d} results with more available")
def step_inbox_returns_n_with_more(context, n):
    context.mock_inbox_results = {
        "items": [
            {
                "s3_key": f"inbox_photo_{i}.jpg",
                "url": f"https://presigned.example.com/inbox_photo_{i}.jpg",
                "thumbnail_url": f"https://thumbnails.example.com/thumbnails/inbox_photo_{i}.webp",
            }
            for i in range(n)
        ],
        "next_cursor": 42,
    }
    context.mock_inbox_second_page = {
        "items": [
            {
                "s3_key": f"inbox_photo_{n + i}.jpg",
                "url": f"https://presigned.example.com/inbox_photo_{n + i}.jpg",
                "thumbnail_url": f"https://thumbnails.example.com/thumbnails/inbox_photo_{n + i}.webp",
            }
            for i in range(n)
        ],
        "next_cursor": None,
    }


@given("the tags API returns {tags_json}")
def step_tags_returns(context, tags_json):
    context.mock_tags = json.loads(tags_json)


@given("the remove-tag API accepts requests")
def step_remove_tag_api_accepts(context):
    pass  # handled unconditionally in the lambda route mock


@given("the remove-tag API returns an error")
def step_remove_tag_api_error(context):
    context.mock_remove_tag_error = True


@given("the add-tags API accepts requests")
def step_add_tags_api_accepts(context):
    pass  # handled unconditionally in the lambda route mock


@given("the add-tags API returns an error")
def step_add_tags_api_error(context):
    context.mock_add_tags_error = True


@given("the search API returns {n:d} result")
@given("the search API returns {n:d} results")
def step_search_returns_n(context, n):
    context.mock_results = [
        {
            "s3_key": f"photo_{i}.jpg",
            "url": f"https://presigned.example.com/photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{i}.webp",
            "tags": ["floral", "outdoor"],
        }
        for i in range(n)
    ]
    context.mock_search_next_cursor = None
    context.mock_search_second_page = None


@given("the search API returns {n:d} results with more available")
def step_search_returns_n_with_more(context, n):
    context.mock_results = [
        {
            "s3_key": f"photo_{i}.jpg",
            "url": f"https://presigned.example.com/photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{i}.webp",
            "tags": ["floral", "outdoor"],
        }
        for i in range(n)
    ]
    context.mock_search_next_cursor = "some-cursor-value"
    context.mock_search_second_page = [
        {
            "s3_key": f"photo_{n + i}.jpg",
            "url": f"https://presigned.example.com/photo_{n + i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{n + i}.webp",
            "tags": ["floral", "outdoor"],
        }
        for i in range(n)
    ]


# ── Page open ────────────────────────────────────────────────────────────────

@when("I open the inbox page")
def step_open_inbox(context):
    page = context.browser.new_page()
    context.page = page
    page.add_init_script("window.INFINITE_SCROLL = false;")

    def handle_lambda(route, request):
        if "/process-inbox" in request.url:
            if getattr(context, "mock_process_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"success": True}))
        elif "/archive-inbox" in request.url:
            if getattr(context, "mock_archive_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"success": True}))
        else:
            if "cursor=" in request.url and hasattr(context, "mock_inbox_second_page"):
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(context.mock_inbox_second_page))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(context.mock_inbox_results))

    page.route("**lambda-url**", handle_lambda)
    page.goto(INBOX_HTML.as_uri())
    page.wait_for_selector("#photo-grid")


@when("I open the inbox page with infinite scroll enabled")
def step_open_inbox_infinite_scroll(context):
    # Use a narrow viewport so 3 grid items (stacked vertically) push the
    # scroll sentinel below the fold, requiring an explicit scroll to trigger load.
    page = context.browser.new_page(viewport={"width": 400, "height": 400})
    context.page = page
    page.add_init_script("window.INFINITE_SCROLL = true;")

    def handle_lambda(route, request):
        if "/process-inbox" in request.url:
            if getattr(context, "mock_process_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"success": True}))
        elif "/archive-inbox" in request.url:
            if getattr(context, "mock_archive_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"success": True}))
        else:
            if "cursor=" in request.url and hasattr(context, "mock_inbox_second_page"):
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(context.mock_inbox_second_page))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(context.mock_inbox_results))

    page.route("**lambda-url**", handle_lambda)
    page.goto(INBOX_HTML.as_uri())
    page.wait_for_selector("#photo-grid")


@when("I scroll to the bottom of the page")
def step_scroll_to_bottom(context):
    context.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    context.page.wait_for_timeout(600)


@when("I open the frontend")
def step_open_frontend(context):
    page = context.browser.new_page()
    context.page = page

    def handle_lambda(route, request):
        if "/tags" in request.url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(context.mock_tags),
            )
        elif "/remove-tag" in request.url:
            if getattr(context, "mock_remove_tag_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"removed": True}))
        elif "/add-tags" in request.url:
            if getattr(context, "mock_add_tags_error", False):
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"error": "Internal Server Error"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"added": 1}))
        else:
            body = json.loads(request.post_data or "{}")
            if body.get("cursor") and getattr(context, "mock_search_second_page", None) is not None:
                payload = {
                    "items": context.mock_search_second_page,
                    "next_cursor": None,
                    "total": len(context.mock_results) + len(context.mock_search_second_page),
                }
            else:
                payload = {
                    "items": context.mock_results,
                    "next_cursor": getattr(context, "mock_search_next_cursor", None),
                    "total": len(context.mock_results),
                }
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            )

    # Intercept all requests to the Lambda Function URL (tags + search).
    page.route("**lambda-url**", handle_lambda)
    page.goto(FRONTEND_HTML.as_uri())

    # Wait for suggestions to finish loading before proceeding.
    if context.mock_tags:
        page.wait_for_selector(".suggestion")
    else:
        page.wait_for_selector("#suggestions")


# ── Interactions ─────────────────────────────────────────────────────────────

@when('I click the "{tag}" suggestion')
def step_click_suggestion(context, tag):
    context.page.get_by_role("button", name=tag, exact=True).click()
    # Wait for search debounce (400 ms) + mock response to settle.
    context.page.wait_for_timeout(600)


@when('I type "{tag}" in the tag input and press Enter')
def step_type_tag_enter(context, tag):
    context.page.locator("#tag-input").fill(tag)
    context.page.keyboard.press("Enter")
    context.page.wait_for_timeout(600)


@when('I remove the "{tag}" chip')
def step_remove_chip(context, tag):
    context.page.get_by_label(f"Remove {tag}").click()
    context.page.wait_for_timeout(200)


@when("I click the first photo")
def step_click_first_photo(context):
    context.page.locator(".grid-item img").first.wait_for()
    context.page.locator(".grid-item img").first.click()


@when("I click the lightbox close button")
def step_click_lightbox_close(context):
    context.page.locator("#lightbox-close").click()


@when("I press Escape")
def step_press_escape(context):
    context.page.keyboard.press("Escape")


@when("I click the lightbox backdrop")
def step_click_lightbox_backdrop(context):
    # Click the top-left corner of the overlay — outside the image.
    context.page.locator("#lightbox").click(position={"x": 5, "y": 5})


# ── Assertions ───────────────────────────────────────────────────────────────

@then('I see the status message "{message}"')
def step_see_status_message(context, message):
    locator = context.page.locator("#status")
    locator.wait_for()
    actual = locator.inner_text()
    assert actual == message, f"Expected status {message!r}, got {actual!r}"


@then("the photo grid is empty")
def step_grid_empty(context):
    assert context.page.locator(".grid-item").count() == 0


@then('I see a suggestion button for "{tag}"')
def step_see_suggestion(context, tag):
    context.page.get_by_role("button", name=tag, exact=True).wait_for()


@then('a chip appears for "{tag}"')
def step_chip_appears(context, tag):
    context.page.locator(".chip", has_text=tag).wait_for()


@then("no chips are shown")
def step_no_chips(context):
    assert context.page.locator(".chip").count() == 0


@then("I see {n:d} photos in the grid")
def step_see_n_photos(context, n):
    context.page.wait_for_function(
        f"document.querySelectorAll('.grid-item').length >= {n}",
        timeout=2000,
    )
    count = context.page.locator(".grid-item").count()
    assert count == n, f"Expected {n} photos, got {count}"


@then("the lightbox is visible")
def step_lightbox_visible(context):
    context.page.locator("#lightbox").wait_for(state="visible")


@then("the lightbox is hidden")
def step_lightbox_hidden(context):
    context.page.locator("#lightbox").wait_for(state="hidden")



def _inbox_items(context):
    """Return the list of inbox items regardless of envelope format."""
    results = getattr(context, "mock_inbox_results", None)
    if isinstance(results, dict):
        return results["items"]
    if isinstance(results, list):
        return results
    return context.mock_results


@then("the grid images use the thumbnail URL")
def step_grid_uses_thumbnail_url(context):
    img = context.page.locator(".grid-item img").first
    img.wait_for()
    src = img.get_attribute("src")
    results = _inbox_items(context) if getattr(context, "mock_inbox_results", None) else context.mock_results
    expected = results[0]["thumbnail_url"]
    assert src == expected, f"Expected thumbnail URL {expected!r}, got {src!r}"


@then("the lightbox shows the full-size URL")
def step_lightbox_shows_full_url(context):
    src = context.page.locator("#lightbox-img").get_attribute("src")
    if getattr(context, "mock_inbox_results", None):
        results = _inbox_items(context)
    else:
        results = context.mock_results
    expected = results[0]["url"]
    assert src == expected, f"Expected full-size URL {expected!r}, got {src!r}"


@then("the lightbox shows the photo's tags")
def step_lightbox_shows_tags(context):
    tags = context.mock_results[0]["tags"]
    for tag in tags:
        locator = context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}')")
        assert locator.count() > 0, f"Tag {tag!r} not found in lightbox"


@when('I click remove on the "{tag}" lightbox tag')
def step_click_remove_lightbox_tag(context, tag):
    context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}') button").click()
    context.page.wait_for_timeout(300)


@then('the "{tag}" tag is no longer shown in the lightbox')
def step_tag_not_in_lightbox(context, tag):
    locator = context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}')")
    assert locator.count() == 0, f"Expected tag {tag!r} to be gone from lightbox"


@then('the "{tag}" tag is still shown in the lightbox')
def step_tag_still_in_lightbox(context, tag):
    locator = context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}')")
    assert locator.count() > 0, f"Expected tag {tag!r} to still be in lightbox"


@then('"{tag}" is not shown as a tag in the lightbox')
def step_tag_absent_in_lightbox(context, tag):
    locator = context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}')")
    assert locator.count() == 0, f"Expected tag {tag!r} to not be in lightbox"


@then('the lightbox shows an "Add tag..." chip')
def step_lightbox_shows_add_tag_chip(context):
    context.page.locator("#lightbox-tags .add-tag-chip").wait_for()


@when('I click the "Add tag..." chip in the lightbox')
def step_click_add_tag_chip(context):
    context.page.locator("#lightbox-tags .add-tag-chip").click()


@then("a tag input field is visible in the lightbox")
def step_tag_input_visible(context):
    context.page.locator("#lightbox-tags .lightbox-tag-input").wait_for(state="visible")


@when('I type "{tag}" in the lightbox tag input and press Enter')
def step_type_lightbox_tag_enter(context, tag):
    context.page.locator("#lightbox-tags .lightbox-tag-input").fill(tag)
    context.page.keyboard.press("Enter")
    context.page.wait_for_timeout(300)


@then('"{tag}" is shown as a tag in the lightbox')
def step_tag_shown_in_lightbox(context, tag):
    context.page.locator(f"#lightbox-tags .lightbox-tag:text('{tag}')").wait_for()


# ── Inbox actions ─────────────────────────────────────────────────────────────

@given("the process-inbox API accepts requests")
def step_process_inbox_api_accepts(context):
    pass  # handled in step_open_inbox mock routing


@given("the process-inbox API returns an error")
def step_process_inbox_api_error(context):
    context.mock_process_error = True


@given("the archive-inbox API accepts requests")
def step_archive_inbox_api_accepts(context):
    pass  # handled in step_open_inbox mock routing


@given("the archive-inbox API returns an error")
def step_archive_inbox_api_error(context):
    context.mock_archive_error = True


@when('I click the "Process" button in the lightbox')
def step_click_process_button(context):
    context.page.get_by_role("button", name="Process", exact=True).click()
    context.page.wait_for_timeout(400)


@when('I click the "Archive" button in the lightbox')
def step_click_archive_button(context):
    context.page.get_by_role("button", name="Archive", exact=True).click()
    context.page.wait_for_timeout(400)


@then('the lightbox shows a "Process" button')
def step_lightbox_shows_process_button(context):
    context.page.locator("#lightbox").get_by_role("button", name="Process").wait_for()


@then('the lightbox shows an "Archive" button')
def step_lightbox_shows_archive_button(context):
    context.page.locator("#lightbox").get_by_role("button", name="Archive").wait_for()


@then("the lightbox shows an error message")
def step_lightbox_shows_error(context):
    context.page.locator("#lightbox-error").wait_for(state="visible")


@then('the "Load more" button is visible')
def step_load_more_visible(context):
    context.page.locator("#load-more-btn").wait_for(state="visible")


@then('the "Load more" button is hidden')
def step_load_more_hidden(context):
    btn = context.page.locator("#load-more-btn")
    btn.wait_for(state="attached")
    assert btn.is_hidden(), "Expected 'Load more' button to be hidden"


@when('I click the "Load more" button')
def step_click_load_more(context):
    context.page.locator("#load-more-btn").click()
    context.page.wait_for_timeout(400)


# ── Stats page ────────────────────────────────────────────────────────────────

_FULL_MOCK_STATS = {
    "inbox_count": 7, "photos_count": 142, "db_count": 138, "archived_count": 23,
    "total_photos": 168, "inbox_s3_count": 4200, "processed_s3_count": 142,
    "thumbnail_count": 130, "orphaned_thumbnails": 2, "orphaned_processed": 3,
    "orphaned_inbox": 4, "top_tags": [],
}


@given("the stats API returns full mock stats")
def step_stats_api_returns_full(context):
    context.mock_stats = dict(_FULL_MOCK_STATS)
    context.mock_stats_error = False


@given("the stats API returns top_tags {tags_json}")
def step_stats_api_returns_top_tags(context, tags_json):
    context.mock_stats = {**_FULL_MOCK_STATS, "top_tags": json.loads(tags_json)}
    context.mock_stats_error = False


@given("the stats API returns an error")
def step_stats_api_error(context):
    context.mock_stats_error = True


_STAT_PATH_MAP = {
    "inbox-count": "inbox_count",
    "db-count": "db_count",
    "archived-count": "archived_count",
    "inbox-s3-count": "inbox_s3_count",
    "processed-s3-count": "processed_s3_count",
    "thumbnail-count": "thumbnail_count",
    "orphaned-thumbnails": "orphaned_thumbnails",
    "orphaned-processed": "orphaned_processed",
    "orphaned-inbox": "orphaned_inbox",
    "top-tags": "top_tags",
}


@when("I open the stats page")
def step_open_stats(context):
    page = context.browser.new_page()
    context.page = page

    def handle_lambda(route, request):
        if getattr(context, "mock_stats_error", False):
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"error": "Internal Server Error"}))
            return
        url = request.url
        # Check mismatch before inbox-count to avoid substring collision
        if "/stats/inbox-count-mismatch" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"s3_count": 0, "db_count": 0}))
            return
        for path_seg, key in _STAT_PATH_MAP.items():
            if f"/stats/{path_seg}" in url:
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"value": context.mock_stats[key]}))
                return
        route.fulfill(status=404, content_type="application/json",
                      body=json.dumps({"error": "Not found"}))

    page.route("**lambda-url**", handle_lambda)
    page.goto(STATS_HTML.as_uri())
    # Wait for at least one stat to load (either a value or "err")
    page.wait_for_function(
        "document.getElementById('inbox-count') && "
        "document.getElementById('inbox-count').textContent.trim() !== '\u2014'",
        timeout=5000,
    )


@then("I see the inbox count as {n:d}")
def step_see_inbox_count(context, n):
    locator = context.page.locator("#inbox-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected inbox count {n}, got {actual!r}"


@then("I see the photos count as {n:d}")
def step_see_photos_count(context, n):
    locator = context.page.locator("#photos-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected photos count {n}, got {actual!r}"


@then("I see the db count as {n:d}")
def step_see_db_count(context, n):
    locator = context.page.locator("#db-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected db count {n}, got {actual!r}"


@then("I see the archived count as {n:d}")
def step_see_archived_count(context, n):
    locator = context.page.locator("#archived-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected archived count {n}, got {actual!r}"


@then("I see the total photos count as {n:d}")
def step_see_total_photos_count(context, n):
    locator = context.page.locator("#total-photos-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected total photos count {n}, got {actual!r}"


@then("I see the inbox s3 count as {n:d}")
def step_see_inbox_s3_count(context, n):
    locator = context.page.locator("#inbox-s3-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected inbox s3 count {n}, got {actual!r}"


@then("I see the processed s3 count as {n:d}")
def step_see_processed_s3_count(context, n):
    locator = context.page.locator("#processed-s3-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected processed s3 count {n}, got {actual!r}"


@then("I see the thumbnail count as {n:d}")
def step_see_thumbnail_count(context, n):
    locator = context.page.locator("#thumbnail-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected thumbnail count {n}, got {actual!r}"


@then("I see the orphaned thumbnails count as {n:d}")
def step_see_orphaned_thumbnails(context, n):
    locator = context.page.locator("#orphaned-thumbnails-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected orphaned thumbnails count {n}, got {actual!r}"


@then("I see the orphaned processed count as {n:d}")
def step_see_orphaned_processed(context, n):
    locator = context.page.locator("#orphaned-processed-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected orphaned processed count {n}, got {actual!r}"


@then("I see the orphaned inbox count as {n:d}")
def step_see_orphaned_inbox(context, n):
    locator = context.page.locator("#orphaned-inbox-count")
    locator.wait_for()
    actual = locator.inner_text().strip()
    assert actual == str(n), f"Expected orphaned inbox count {n}, got {actual!r}"


@then('the stat card "{label}" has an info icon')
def step_stat_card_has_info_icon(context, label):
    # Use exact label match via the .stat-label span to avoid partial text collisions
    card = context.page.locator(".stat-card").filter(
        has=context.page.locator(".stat-label", has_text=label)
    ).first
    card.wait_for()
    icon = card.locator(".info-icon")
    assert icon.count() > 0, f"Expected info icon in stat card '{label}', found none"


@then('I see "{tag}" in the top tags list')
def step_see_tag_in_top_tags(context, tag):
    locator = context.page.locator("#top-tags-list")
    locator.wait_for()
    text = locator.inner_text()
    assert tag in text, f"Expected {tag!r} in top tags list, got: {text!r}"


@then("I see a stats error message")
def step_see_stats_error(context):
    context.page.locator("#stats-error").wait_for(state="visible")
