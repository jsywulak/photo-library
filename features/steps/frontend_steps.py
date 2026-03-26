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


# ── Mock setup ───────────────────────────────────────────────────────────────

@given("the inbox API returns {n:d} result")
@given("the inbox API returns {n:d} results")
def step_inbox_returns_n(context, n):
    context.mock_inbox_results = [
        {
            "s3_key": f"inbox_photo_{i}.jpg",
            "url": f"https://presigned.example.com/inbox_photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/inbox_photo_{i}.webp",
        }
        for i in range(n)
    ]


@given("the tags API returns {tags_json}")
def step_tags_returns(context, tags_json):
    context.mock_tags = json.loads(tags_json)


@given("the remove-tag API accepts requests")
def step_remove_tag_api_accepts(context):
    pass  # handled unconditionally in the lambda route mock


@given("the add-tags API accepts requests")
def step_add_tags_api_accepts(context):
    pass  # handled unconditionally in the lambda route mock


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


# ── Page open ────────────────────────────────────────────────────────────────

@when("I open the inbox page")
def step_open_inbox(context):
    page = context.browser.new_page()
    context.page = page

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
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(context.mock_inbox_results))

    page.route("**lambda-url**", handle_lambda)
    page.goto(INBOX_HTML.as_uri())
    page.wait_for_selector("#photo-grid")


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
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"removed": True}),
            )
        elif "/add-tags" in request.url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"added": 1}),
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(context.mock_results),
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
    context.page.locator(".grid-item").first.wait_for()
    count = context.page.locator(".grid-item").count()
    assert count == n, f"Expected {n} photos, got {count}"


@then("the lightbox is visible")
def step_lightbox_visible(context):
    context.page.locator("#lightbox").wait_for(state="visible")


@then("the lightbox is hidden")
def step_lightbox_hidden(context):
    context.page.locator("#lightbox").wait_for(state="hidden")



@then("the grid images use the thumbnail URL")
def step_grid_uses_thumbnail_url(context):
    img = context.page.locator(".grid-item img").first
    img.wait_for()
    src = img.get_attribute("src")
    results = getattr(context, "mock_inbox_results", None) or context.mock_results
    expected = results[0]["thumbnail_url"]
    assert src == expected, f"Expected thumbnail URL {expected!r}, got {src!r}"


@then("the lightbox shows the full-size URL")
def step_lightbox_shows_full_url(context):
    src = context.page.locator("#lightbox-img").get_attribute("src")
    results = context.mock_results or context.mock_inbox_results
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
