@infrastructure
Feature: Thumbnail backfill script
  The backfill script generates thumbnails for all processed photos
  that don't already have one.

  Scenario: Backfill creates thumbnails for photos without one
    Given a processed photo exists in the database and S3
    When the backfill script runs for that photo
    Then a thumbnail should exist in the thumbnail bucket for that photo

  Scenario: Backfill skips photos that already have a thumbnail
    Given a processed photo exists in the database and S3
    And a thumbnail already exists for the photo
    When the backfill script runs for that photo
    Then the backfill result should show 0 thumbnailed and 1 skipped

  Scenario: Inbox backfill creates thumbnails for inbox photos without one
    Given an inbox photo exists in the database and inbox S3 bucket
    When the inbox backfill script runs for that photo
    Then a thumbnail should exist in the thumbnail bucket for that photo

  Scenario: Inbox backfill skips photos that already have a thumbnail
    Given an inbox photo exists in the database and inbox S3 bucket
    And a thumbnail already exists for the photo
    When the inbox backfill script runs for that photo
    Then the backfill result should show 0 thumbnailed and 1 skipped

  Scenario: Backfill sets source-hash metadata on existing thumbnails
    Given a processed photo exists in the database and S3
    And a thumbnail already exists for the photo
    When the metadata backfill runs for that photo
    Then the thumbnail should have source-hash metadata

  Scenario: Inbox backfill sets source-hash metadata on existing thumbnails
    Given an inbox photo exists in the database and inbox S3 bucket
    And a thumbnail already exists for the photo
    When the inbox metadata backfill runs for that photo
    Then the thumbnail should have source-hash metadata
