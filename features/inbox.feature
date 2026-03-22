@frontend
Feature: Inbox UI
  The inbox page shows unprocessed photos from the inbox bucket
  in a photo grid with a lightbox viewer. There is no search bar or tag chips.

  Background:
    Given the inbox API returns 0 results

  Scenario: Inbox page shows all inbox photos
    Given the inbox API returns 3 results
    When I open the inbox page
    Then I see 3 photos in the grid

  Scenario: Inbox grid images use the thumbnail URL
    Given the inbox API returns 1 result
    When I open the inbox page
    Then the grid images use the thumbnail URL

  Scenario: Inbox page shows a message when empty
    When I open the inbox page
    Then I see the status message "No photos in inbox."

  Scenario: Clicking a photo opens the lightbox
    Given the inbox API returns 1 result
    When I open the inbox page
    And I click the first photo
    Then the lightbox is visible
    And the lightbox shows the full-size URL

  Scenario: Closing the lightbox with the × button
    Given the inbox API returns 1 result
    When I open the inbox page
    And I click the first photo
    And I click the lightbox close button
    Then the lightbox is hidden

  Scenario: Closing the lightbox with Escape
    Given the inbox API returns 1 result
    When I open the inbox page
    And I click the first photo
    And I press Escape
    Then the lightbox is hidden

  Scenario: Closing the lightbox by clicking the backdrop
    Given the inbox API returns 1 result
    When I open the inbox page
    And I click the first photo
    And I click the lightbox backdrop
    Then the lightbox is hidden
