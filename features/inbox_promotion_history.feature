@infrastructure
Feature: Promoting an inbox photo preserves its history
  inbox.process_inbox_photo UPDATEs the photos row in place when moving from
  the inbox bucket to the photos bucket — preserving the row's id, captured_at,
  original_filename, content_hash, and prior photo_events. Today the row is
  DELETEd and the photos-bucket processor INSERTs a fresh one with a new id.

  Scenario: Promotion keeps the same photos.id
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the photos row id should be preserved across promotion
    And the photos row bucket should now be "photo-tagging-photos"

  Scenario: Promotion preserves captured_at, original_filename, content_hash
    Given the inbox Lambda is deployed
    And a photo with captured_at "2024-06-15 12:00:00", original_filename "vacation.jpg", and a known content_hash exists in the inbox
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the photos row captured_at should still be "2024-06-15 12:00:00"
    And the photos row original_filename should still be "vacation.jpg"
    And the photos row content_hash should still be the original

  Scenario: Promotion preserves prior photo_events
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    And a "received" photo_events row exists for the inbox photo
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And the prior "received" photo_events row should still reference the same photo_id
    And a "promoted" photo_events row should exist for the same photo_id
