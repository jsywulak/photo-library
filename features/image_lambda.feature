@infrastructure
Feature: Image Handler Lambda
  The image handler Lambda fires when a photo is uploaded to the upload
  staging bucket. It computes the content hash, generates a hash-keyed
  thumbnail, copies the photo to the inbox bucket as {hash}.jpg, and
  deletes the original from the upload bucket.

  Scenario: Image handler Lambda exists and is active
    Given the image handler Lambda is deployed
    Then the image handler function should be active

  Scenario: Image handler Lambda is triggered by S3 uploads via EventBridge
    Given the image handler Lambda is deployed
    Then an EventBridge rule should trigger the image handler Lambda on S3 uploads to the upload bucket

  Scenario: Image handler processes a photo end-to-end
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then the photo should appear in the inbox bucket with a hash-based key
    And a thumbnail should exist in the thumbnail bucket with the hash-based key
    And the original photo should no longer exist in the upload bucket

  Scenario: Image handler returns the correct content_hash
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then the Lambda should return the expected content_hash

  Scenario: Image handler preserves the original filename as S3 metadata
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then the inbox object should have original-filename metadata matching the upload key

  Scenario: Thumbnail created by image handler has source-hash metadata
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then the inbox thumbnail should have source-hash metadata matching the photo's SHA-256

  Scenario: Image handler writes a photos row to Neon when a photo is received
    Given the image handler Lambda is deployed
    And a test JPEG with EXIF DateTimeOriginal "2024:06:15 12:00:00" is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then a photos row should exist in Neon for the inbox key with bucket "photo-tagging-inbox"
    And the photos row content_hash should match the uploaded SHA-256
    And the photos row captured_at should be "2024-06-15 12:00:00"
    And the photos row original_filename should match the upload key

  Scenario: Image handler is idempotent when the same content arrives twice
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    And the image handler Lambda processes the photo
    When the same photo content is uploaded to the upload bucket under a different key
    And the image handler Lambda processes the new upload
    Then exactly one photos row should exist in Neon for the content_hash with bucket "photo-tagging-inbox"
