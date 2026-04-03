@e2e
Feature: Live search page
  The live search page at FRONTEND_DOMAIN shows processed photos.
  Uploading a photo to the photos bucket triggers the processor Lambda via
  EventBridge, and the result is then findable by tag on the live search page.

  Scenario: Processed photo appears in live search results
    Given PXL_20260319_193406856.jpg is uploaded to the photos bucket
    Then the photo should be processed and stored in the database within 120 seconds
    When I open the live search page and search by a tag the photo received
    Then the test photo appears in the search results

  Scenario: Live search with many results shows a "Load more" button
    Given a tag exists in the Neon database with more than 200 photos
    When I open the live search page and search for that tag
    Then I see 200 photos in the grid
    And the "Load more" button is visible
    When I click the "Load more" button on the search page
    Then I see more than 200 photos in the grid
