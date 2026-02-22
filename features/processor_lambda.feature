@infrastructure
Feature: Processor Lambda
  The processor Lambda reads photos from S3, tags them via the Anthropic API,
  and stores results in the database.

  Scenario: Processor Lambda exists and is active
    Given the processor Lambda is deployed
    Then the function should be active

  Scenario: Processing a photo stores results in the database
    Given the processor Lambda is deployed
    And a test photo is uploaded to S3
    When the Lambda processes the photo
    Then the photo should be stored in the Neon database
    And the photo should have tags in the Neon database
