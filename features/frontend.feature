@frontend
Feature: Frontend UI
  The single-page app supports tag-based search and shows results
  in a photo grid with a lightbox viewer.

  Background:
    Given the tags API returns ["floral", "outdoor", "wire"]
    And the search API returns 0 results

  Scenario: Initial state shows a prompt
    When I open the frontend
    Then I see the status message "Add a tag to search."
    And the photo grid is empty

  Scenario: Tag suggestions appear on load
    When I open the frontend
    Then I see a suggestion button for "floral"
    And I see a suggestion button for "outdoor"
    And I see a suggestion button for "wire"

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

  Scenario: Lightbox shows an "Add tag..." chip
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    Then the lightbox shows an "Add tag..." chip

  Scenario: Clicking "Add tag..." turns it into a text input
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the "Add tag..." chip in the lightbox
    Then a tag input field is visible in the lightbox

  Scenario: Typing a tag in the lightbox and pressing Enter adds it
    Given the search API returns 1 result
    And the add-tags API accepts requests
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the "Add tag..." chip in the lightbox
    And I type "roses" in the lightbox tag input and press Enter
    Then "roses" is shown as a tag in the lightbox

  Scenario: Clicking remove on a lightbox tag removes it
    Given the search API returns 1 result
    And the remove-tag API accepts requests
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click remove on the "floral" lightbox tag
    Then the "floral" tag is no longer shown in the lightbox

  Scenario: Remove tag failure keeps the tag in the lightbox
    Given the search API returns 1 result
    And the remove-tag API returns an error
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click remove on the "floral" lightbox tag
    Then the "floral" tag is still shown in the lightbox

  Scenario: Add tag failure removes the chip from the lightbox
    Given the search API returns 1 result
    And the add-tags API returns an error
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the "Add tag..." chip in the lightbox
    And I type "roses" in the lightbox tag input and press Enter
    Then "roses" is not shown as a tag in the lightbox

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

  Scenario: "Load more" button is hidden when all results fit on one page
    Given the search API returns 3 results
    When I open the frontend
    And I click the "floral" suggestion
    Then I see 3 photos in the grid
    And the "Load more" button is hidden

  Scenario: "Load more" button appears when more results are available
    Given the search API returns 3 results with more available
    When I open the frontend
    And I click the "floral" suggestion
    Then I see 3 photos in the grid
    And the "Load more" button is visible

  Scenario: Clicking "Load more" appends the next page to the grid
    Given the search API returns 3 results with more available
    When I open the frontend
    And I click the "floral" suggestion
    Then I see 3 photos in the grid
    When I click the "Load more" button
    Then I see 6 photos in the grid
    And the "Load more" button is hidden

  Scenario: Lightbox shows an "Archive" button
    Given the search API returns 1 result
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    Then the lightbox shows an "Archive" button

  Scenario: Clicking "Archive" closes the lightbox and removes the photo from the grid
    Given the search API returns 1 result
    And the archive API accepts requests
    When I open the frontend
    And I click the "floral" suggestion
    And I click the first photo
    And I click the "Archive" button in the lightbox
    Then the lightbox is hidden
    And the photo grid is empty
