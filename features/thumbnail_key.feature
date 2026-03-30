@local
Feature: Thumbnail key uniqueness
  Photos in different directories with the same filename must generate
  different thumbnail keys. Using only the filename stem (ignoring the
  directory) causes collisions: the later-thumbnailed photo overwrites
  the earlier one, leaving the earlier photo's grid thumbnail pointing
  to the wrong image.

  Scenario: Flat key produces the expected thumbnail key
    Given the s3_key is "photo.jpg"
    Then the thumbnail key should be "thumbnails/photo.webp"

  Scenario: Path key preserves the directory
    Given the s3_key is "2024/IMG_001.jpg"
    Then the thumbnail key should be "thumbnails/2024/IMG_001.webp"

  Scenario: Photos with the same filename in different directories get different thumbnail keys
    Given the s3_key is "2024/IMG_001.jpg"
    And another s3_key is "2023/IMG_001.jpg"
    Then their thumbnail keys should be different
