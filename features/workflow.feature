@infrastructure
Feature: End-to-end photo workflow
  Uploading a photo to the photos bucket triggers automatic processing
  and thumbnailing via EventBridge.

  Scenario: Uploading a photo results in tags and a thumbnail
    Given a photo is uploaded to the photos bucket
    Then the photo should be processed and stored in the database within 120 seconds
    And a thumbnail should exist in the thumbnail bucket within 60 seconds
