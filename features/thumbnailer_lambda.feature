@infrastructure
Feature: Thumbnailer Lambda
  The thumbnailer Lambda reads photos from S3, generates a 400x400 WebP
  thumbnail, and writes it to the thumbnail bucket.

  Scenario: Thumbnailer Lambda exists and is active
    Given the thumbnailer Lambda is deployed
    Then the thumbnailer function should be active

  Scenario: Thumbnailer Lambda is triggered by S3 uploads via EventBridge
    Given the thumbnailer Lambda is deployed
    Then an EventBridge rule should trigger the thumbnailer Lambda on S3 uploads to the photos bucket

  Scenario: Thumbnailing a photo creates a WebP in the thumbnail bucket
    Given the thumbnailer Lambda is deployed
    And a test photo is uploaded to the photos bucket
    When the thumbnailer Lambda processes the photo
    Then a thumbnail should exist in the thumbnail bucket
    And the thumbnail should be a 400x400 WebP

  Scenario: Already-thumbnailed photos are skipped
    Given the thumbnailer Lambda is deployed
    And a test photo is uploaded to the photos bucket
    And a thumbnail already exists for the photo
    When the thumbnailer Lambda processes the photo
    Then the Lambda should return status "skipped"
