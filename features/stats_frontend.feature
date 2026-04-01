@frontend
Feature: Stats dashboard

  Scenario: Stats page shows all metrics
    Given the stats API returns full mock stats
    When I open the stats page
    Then I see the inbox count as 7
    And I see the db count as 138
    And I see the archived count as 23
    And I see the total photos count as 168
    And I see the inbox s3 count as 4200
    And I see the processed s3 count as 142
    And I see the thumbnail count as 130
    And I see the orphaned thumbnails count as 2
    And I see the orphaned processed count as 3
    And I see the orphaned inbox count as 4

  Scenario: Stats page shows top tags
    Given the stats API returns top_tags [{"name": "floral", "count": 5}, {"name": "outdoor", "count": 3}]
    When I open the stats page
    Then I see "floral" in the top tags list
    And I see "outdoor" in the top tags list

  Scenario: Stat cards have info icons
    Given the stats API returns full mock stats
    When I open the stats page
    Then the stat card "Inbox" has an info icon

  Scenario: Stats page shows an error message when the API fails
    Given the stats API returns an error
    When I open the stats page
    Then I see a stats error message
