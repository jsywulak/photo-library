@frontend
Feature: Frontend UI
  The single-page app supports tag-based search and shows results
  in a photo grid with a lightbox viewer.

  Background:
    Given the tags API returns ["floral", "outdoor", "indoor"]
    And the search API returns 0 results

  Scenario: Initial state shows a prompt
    When I open the frontend
    Then I see the status message "Add a tag to search."
    And the photo grid is empty

  Scenario: Tag suggestions appear on load
    When I open the frontend
    Then I see a suggestion button for "floral"
    And I see a suggestion button for "outdoor"
    And I see a suggestion button for "indoor"

  Scenario: Clicking a suggestion adds it as a chip
    When I open the frontend
    And I click the "floral" suggestion
    Then a chip appears for "floral"

  Scenario: Typing a tag and pressing Enter adds it as a chip
    When I open the frontend
    And I type "roses" in the tag input and press Enter
    Then a chip appears for "roses"

  Scenario: Removing a chip restores the initial state
    When I open the frontend
    And I type "roses" in the tag input and press Enter
    And I remove the "roses" chip
    Then no chips are shown
    And I see the status message "Add a tag to search."

  Scenario: Search results render as a photo grid
    Given the search API returns 3 results
    When I open the frontend
    And I click the "floral" suggestion
    Then I see 3 photos in the grid

  Scenario: No matching photos shows a message
    When I open the frontend
    And I click the "floral" suggestion
    Then I see the status message "No photos found."

  Scenario: Grid images use the thumbnail URL
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    Then the grid images use the thumbnail URL

  Scenario: Clicking a photo opens the lightbox with the full-size URL
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    Then the lightbox is visible
    And the lightbox shows the full-size URL

  Scenario: Lightbox shows the photo's tags
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    Then the lightbox shows the photo's tags

  Scenario: Clicking remove on a lightbox tag removes it
    Given the search API returns 1 result
    And the remove-tag API accepts requests
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click remove on the "floral" lightbox tag
    Then the "floral" tag is no longer shown in the lightbox

  Scenario: Closing the lightbox with the × button
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the lightbox close button
    Then the lightbox is hidden

  Scenario: Closing the lightbox with Escape
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I press Escape
    Then the lightbox is hidden

  Scenario: Closing the lightbox by clicking the backdrop
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the lightbox backdrop
    Then the lightbox is hidden
