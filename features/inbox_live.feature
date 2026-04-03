@e2e
Feature: Live inbox page
  The live inbox page at FRONTEND_DOMAIN/inbox.html shows real inbox photos
  and lets the user process or archive them via the real inbox Lambda.

  Scenario: Process and archive photos on the live inbox page
    Given two test photos are uploaded to the inbox bucket with current timestamps
    When I open the live inbox page
    Then both test photos are visible in the inbox grid
    When I process the first test photo
    Then the first photo is removed from the inbox grid
    And the first photo exists in the photos bucket
    When I archive the second test photo
    Then the second photo is removed from the inbox grid
    And the second photo is marked archived in Neon
