@infrastructure
Feature: Inbox Lambda
  The inbox Lambda handles listing, processing, and archiving unprocessed
  photos in the inbox S3 bucket.

  Scenario: Inbox Lambda exists and is active
    Given the inbox Lambda is deployed
    Then the inbox function should be active

  Scenario: GET /inbox returns photos from the inbox bucket
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200 v2
    And the response body should contain the inbox photo with a presigned URL v2

  Scenario: GET /inbox includes a thumbnail_url for each result
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200 v2
    And each inbox result should include a thumbnail_url v2

  Scenario: GET /inbox rejects requests with a wrong API key
    Given the inbox Lambda is deployed
    When the inbox Function URL GET /inbox is called with an incorrect API key
    Then the HTTP response status should be 401 v2

  Scenario: GET /inbox returns an empty list when the inbox bucket is empty
    Given the inbox Lambda is deployed
    When the inbox Function URL GET /inbox is called with the correct API key
    Then the HTTP response status should be 200 v2
    And the response body should be a list v2

  Scenario: GET /inbox supports cursor-based pagination
    Given the inbox Lambda is deployed
    When the inbox Function URL GET /inbox is called with limit 2 and the correct API key
    Then the HTTP response status should be 200 v2
    And the inbox response contains 2 items v2
    And the inbox response has a next_cursor v2
    When the inbox Function URL GET /inbox is called with the next cursor and the correct API key
    Then the HTTP response status should be 200 v2
    And the inbox response items do not overlap with the previous page v2

  Scenario: GET /inbox with an invalid cursor returns 400
    Given the inbox Lambda is deployed
    When the inbox Function URL GET /inbox is called with cursor "notanint" and the correct API key
    Then the HTTP response status should be 400 v2

  Scenario: POST /process-inbox uses the content hash as the photos bucket key
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the photos bucket should contain the photo at its hash-based key v2
    And the inbox bucket should no longer contain the original photo v2

  Scenario: POST /archive-inbox soft-deletes a photo from the inbox
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL POST /archive-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the inbox photo should no longer appear in GET /inbox

  Scenario: POST /archive-inbox rejects requests with a wrong API key
    Given the inbox Lambda is deployed
    When the inbox Function URL POST /archive-inbox is called with an incorrect API key
    Then the HTTP response status should be 401 v2

  Scenario: POST /process-inbox rejects requests with a wrong API key
    Given the inbox Lambda is deployed
    When the inbox Function URL POST /process-inbox is called with an incorrect API key
    Then the HTTP response status should be 401 v2

  Scenario: POST /process-inbox propagates S3 metadata onto the photos-bucket object
    Given the inbox Lambda is deployed
    And a photo with captured_at "2024-06-15 12:00:00", original_filename "vacation.jpg", and a known content_hash exists in the inbox
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the photos-bucket object should have content-hash metadata matching the inbox content_hash
    And the photos-bucket object should have original-filename metadata "vacation.jpg"
    And the photos-bucket object should have pipeline-stage metadata "awaiting_review"
