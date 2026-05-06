@local
Feature: photo_events audit log records every action
  Every action taken against a photo is recorded in the photo_events table
  so the system is debuggable, recoverable, and auditable.

  Scenario: Local processor records a "tagged" event after successful tagging
    Given the database is empty
    And a local directory with photos "photo1.jpg"
    When the processor runs
    Then a photo_events row with event_type "tagging_started" should exist for "photo1.jpg"
    And a photo_events row with event_type "tagged" should exist for "photo1.jpg"
    And the "tagged" event details should include the model name

  Scenario: Local processor records a "tag_failed" event when image processing errors
    Given the database is empty
    And a local directory with a corrupted oversized image "broken.jpg"
    When the processor attempts to process the image and fails
    Then a photo_events row with event_type "tag_failed" should exist for "broken.jpg"
    And "broken.jpg" should have processed_at NULL in the database
