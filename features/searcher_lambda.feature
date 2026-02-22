@infrastructure
Feature: Searcher Lambda
  The searcher Lambda queries the database and returns photos ranked by
  how many of the searched tags they match.

  Scenario: Searcher Lambda exists and is active
    Given the searcher Lambda is deployed
    Then the searcher function should be active

  Scenario: Searching returns ranked results
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat, animal, indoor"
    And a photo exists in the Neon database tagged with "cat, outdoor"
    When the Lambda is invoked with tags "cat, animal"
    Then the results should contain both photos
    And the photo with more matching tags should rank higher
