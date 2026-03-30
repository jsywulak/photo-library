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

  Scenario: Search results include a presigned URL
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat"
    When the Lambda is invoked with tags "cat"
    Then each result should include a presigned URL

  Scenario: GET /tags returns a list of tag names
    Given the searcher Lambda is deployed
    When the Function URL GET /tags is called with the correct API key
    Then the HTTP response status should be 200
    And the response body should be a list of strings
    And the response should contain at most 20 tags

  Scenario: GET /tags rejects requests with a wrong API key
    Given the searcher Lambda is deployed
    When the Function URL GET /tags is called with an incorrect API key
    Then the HTTP response status should be 401

  Scenario: Function URL rejects a tags payload that is a string instead of a list
    Given the searcher Lambda is deployed
    When the Function URL is called with a string tags payload and the correct API key
    Then the HTTP response status should be 400

  Scenario: Presigned URL for a photo in S3 is accessible
    Given the searcher Lambda is deployed
    And a photo is uploaded to S3 and tagged in the database with "cat"
    When the Function URL is called with tags "cat" and the correct API key
    Then the HTTP response status should be 200
    And the presigned URL for the photo should return HTTP 200

  Scenario: Search results include a thumbnail URL
    Given the searcher Lambda is deployed
    And a photo is uploaded to S3 and tagged in the database with "cat"
    And a thumbnail exists in the thumbnail bucket for that photo
    When the Lambda is invoked with tags "cat"
    Then each result should include a thumbnail_url

  Scenario: GET /inbox returns photos from the inbox bucket
    Given the searcher Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database
    When the Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200
    And the response body should contain the inbox photo with a presigned URL

  Scenario: GET /inbox includes a thumbnail_url for each result
    Given the searcher Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database
    When the Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200
    And each inbox result should include a thumbnail_url

  Scenario: GET /inbox rejects requests with a wrong API key
    Given the searcher Lambda is deployed
    When the Function URL GET /inbox is called with an incorrect API key
    Then the HTTP response status should be 401

  Scenario: GET /inbox returns an empty list when the inbox bucket is empty
    Given the searcher Lambda is deployed
    When the Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200
    And the response body should be a list

  Scenario: POST /add-tags adds new tags to a photo
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "animal"
    When the Function URL POST /add-tags is called for the photo with tags "indoor, cozy" and the correct API key
    Then the HTTP response status should be 200
    And searching for "indoor" via the Lambda should return the photo

  Scenario: POST /add-tags restores a previously removed tag
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat, animal"
    When the Function URL POST /remove-tag is called for the photo with tag "cat" and the correct API key
    Then the HTTP response status should be 200
    And searching for "cat" via the Lambda should not return the photo
    When the Function URL POST /add-tags is called for the photo with tags "cat" and the correct API key
    Then the HTTP response status should be 200
    And searching for "cat" via the Lambda should still return the photo

  Scenario: POST /add-tags rejects requests with a wrong API key
    Given the searcher Lambda is deployed
    When the Function URL POST /add-tags is called with an incorrect API key
    Then the HTTP response status should be 401

  Scenario: POST /remove-tag logically removes a tag from a photo
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat, animal"
    When the Function URL POST /remove-tag is called for the photo with tag "cat" and the correct API key
    Then the HTTP response status should be 200
    And searching for "cat" via the Lambda should not return the photo
    And searching for "animal" via the Lambda should still return the photo

  Scenario: POST /remove-tag rejects requests with a wrong API key
    Given the searcher Lambda is deployed
    When the Function URL POST /remove-tag is called with an incorrect API key
    Then the HTTP response status should be 401

  Scenario: GET /inbox supports cursor-based pagination
    Given the searcher Lambda is deployed
    When the Function URL GET /inbox is called with limit 2 and the correct API key
    Then the HTTP response status should be 200
    And the inbox response contains 2 items
    And the inbox response has a next_cursor
    When the Function URL GET /inbox is called with the next cursor and the correct API key
    Then the HTTP response status should be 200
    And the inbox response items do not overlap with the previous page

  Scenario: GET /inbox with an invalid cursor returns 400
    Given the searcher Lambda is deployed
    When the Function URL GET /inbox is called with cursor "notanint" and the correct API key
    Then the HTTP response status should be 400

  Scenario: POST /process-inbox uses the content hash as the photos bucket key
    Given the searcher Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database
    When the Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200
    And the photos bucket should contain the photo at its hash-based key
    And the inbox bucket should no longer contain the original photo
