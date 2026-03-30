@infrastructure
Feature: Processor v2 Lambda
  The processor v2 Lambda reads photos from S3, tags them via the Anthropic API,
  and stores results in the database. This is the new standalone lambda being
  stood up alongside the original processor. EventBridge wiring comes later.

  Scenario: Processor v2 Lambda exists and is active
    Given the processor v2 Lambda is deployed
    Then the processor v2 function should be active

  Scenario: Processor v2 Lambda is triggered by S3 uploads via EventBridge
    Given the processor v2 Lambda is deployed
    Then an EventBridge rule should trigger the processor v2 Lambda on S3 uploads to the photos bucket

  Scenario: Processing a photo stores results in the database v2
    Given the processor v2 Lambda is deployed
    And a test photo is uploaded to S3 v2
    When the v2 Lambda processes the photo
    Then the v2 photo should be stored in the Neon database
    And the v2 photo should have tags in the Neon database
