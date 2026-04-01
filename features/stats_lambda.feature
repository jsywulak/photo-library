@infrastructure
Feature: Stats Lambda

  Scenario: Unauthenticated request returns 401
    Given the stats Lambda is deployed
    When the stats Function URL GET /stats is called with an incorrect API key
    Then the stats HTTP response status should be 401

  Scenario: GET /stats returns all expected metrics
    Given the stats Lambda is deployed
    When the stats Function URL GET /stats is called with the correct API key
    Then the stats HTTP response status should be 200
    And the stats response body contains all numeric stat fields as non-negative integers
    And the stats response body contains top_tags as a list
