@infrastructure
Feature: Full upload pipeline
  Uploading a photo to the upload bucket triggers the image handler Lambda via
  EventBridge, which creates a thumbnail and moves the photo to the inbox.
  Submitting it for processing triggers the processor Lambda which tags it in Neon.

  Scenario: Uploading to the upload bucket triggers the full pipeline
    Given PXL_20260319_193406856.jpg is uploaded to the upload bucket
    Then the photo should appear in the inbox bucket within 60 seconds
    And a thumbnail should exist in the thumbnail bucket within 60 seconds
    When the photo is submitted for processing via the inbox Lambda
    Then the photo should be processed and stored in the database within 120 seconds
    And the photo should have tags in the Neon database
