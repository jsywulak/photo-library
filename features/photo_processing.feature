@local
Feature: Photo processing pipeline
  Photos are ingested from a local directory, checked against the database,
  and new ones are tagged and stored.

  Scenario: Discover photos in a local directory
    Given a local directory with photos "photo1.jpg, photo2.jpg"
    When the processor runs
    Then 2 photos should be discovered

  Scenario: Skip photos already in the database
    Given a local directory with photos "photo1.jpg, photo2.jpg"
    And "photo1.jpg" is already in the database
    When the processor runs
    Then 1 photo should be processed
    And 1 photo should be skipped

  Scenario: New photos are saved to the database
    Given a local directory with photos "photo1.jpg"
    When the processor runs
    Then "photo1.jpg" should be saved to the database

  Scenario: Tags are stored for new photos
    Given a local directory with photos "photo1.jpg"
    When the processor runs
    Then "photo1.jpg" should have tags in the database

  Scenario: Non-JPEG files are skipped and not saved to the database
    Given a local directory with an unsupported file "photo.nef"
    When the processor runs
    Then 0 photos should be processed
    And "photo.nef" should not be saved to the database

  Scenario: Images larger than the base64 limit are resized and tagged successfully
    Given a local directory with an oversized image "large_photo.jpg"
    When the processor runs
    Then 1 photo should be processed
    And "large_photo.jpg" should have tags in the database

  Scenario: Processing errors include the image filename in the log
    Given a local directory with a corrupted oversized image "bad_photo.jpg"
    When the processor attempts to process the image and fails
    Then the error log should include "bad_photo.jpg"

  Scenario: Photos are saved with their source bucket
    Given a local directory with photos "photo1.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "photo1.jpg" should be saved to the database with bucket "photo-tagging-inbox"

  Scenario: Same photo key in different buckets can both be stored
    Given a local directory with photos "photo1.jpg"
    And "photo1.jpg" is already in the database for bucket "photo-tagging-photos"
    When the processor runs for bucket "photo-tagging-inbox"
    Then 1 photo should be processed
    And "photo1.jpg" should be saved to the database with bucket "photo-tagging-inbox"

  Scenario: Inbox photos have captured_at populated from EXIF DateTimeOriginal
    Given a local directory with a JPEG with EXIF DateTimeOriginal "2024:03:15 10:30:00" named "photo_with_exif.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "photo_with_exif.jpg" should have captured_at "2024-03-15 10:30:00" in the database

  Scenario: Inbox photos without EXIF have captured_at as NULL
    Given a local directory with a JPEG without EXIF named "photo_no_exif.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "photo_no_exif.jpg" should have captured_at NULL in the database

  Scenario: Inbox photo arrival stores content_hash in DB
    Given a local directory with a JPEG without EXIF named "hashed.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "hashed.jpg" should have a 64-character content_hash in the database

  Scenario: Inbox photo arrival stores original_filename in DB
    Given a local directory with a JPEG without EXIF named "named.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "named.jpg" should have original_filename set in the database

  Scenario: Photo with duplicate content is skipped when it already exists in the photos bucket
    Given a local directory with a JPEG without EXIF named "duplicate.jpg"
    And the same photo bytes already exist in the photos bucket
    When the processor runs for bucket "photo-tagging-inbox"
    Then 0 photos should be processed
    And 1 photo should be skipped

  Scenario: Uploading duplicate content to the photos bucket under a different key is skipped
    Given a local directory with a JPEG without EXIF named "photo_copy.jpg"
    And the same photo bytes already exist in the photos bucket under a different key
    When the processor runs for bucket "photo-tagging-photos"
    Then 0 photos should be processed
    And 1 photo should be skipped
