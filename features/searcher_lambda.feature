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

  Scenario: Function URL is publicly reachable with a valid API key
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat, animal"
    When the Function URL is called with tags "cat" and the correct API key
    Then the HTTP response status should be 200
    And the response body should contain the photo

  Scenario: Function URL rejects requests with a wrong API key
    Given the searcher Lambda is deployed
    When the Function URL is called with tags "cat" and an incorrect API key
    Then the HTTP response status should be 401
