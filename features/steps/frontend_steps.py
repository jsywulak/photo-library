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


@given("the search API returns {n:d} result")
@given("the search API returns {n:d} results")
def step_search_returns_n(context, n):
    context.mock_results = [
        {
            "s3_key": f"photo_{i}.jpg",
            "url": f"https://presigned.example.com/photo_{i}.jpg",
            "thumbnail_url": f"https://thumbnails.example.com/thumbnails/photo_{i}.webp",
        }
        for i in range(n)
    ]


# ── Page open ────────────────────────────────────────────────────────────────

@when("I open the inbox page")
def step_open_inbox(context):
    page = context.browser.new_page()
    context.page = page

    def handle_lambda(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(context.mock_inbox_results),
        )

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
    expected = context.mock_results[0]["thumbnail_url"]
    assert src == expected, f"Expected thumbnail URL {expected!r}, got {src!r}"


@then("the lightbox shows the full-size URL")
def step_lightbox_shows_full_url(context):
    src = context.page.locator("#lightbox-img").get_attribute("src")
    results = context.mock_results or context.mock_inbox_results
    expected = results[0]["url"]
    assert src == expected, f"Expected full-size URL {expected!r}, got {src!r}"
