@local
Feature: photos.state reflects pipeline lifecycle
  An explicit state column lets the system distinguish "in inbox", "tagged",
  "failed", and "archived" cleanly, without sniffing column nullability.

  Scenario: Photo state advances to "tagged" after successful processing
    Given the database is empty
    And a local directory with photos "photo1.jpg"
    When the processor runs
    Then "photo1.jpg" should have state "tagged" in the database
    And "photo1.jpg" should have tagged_at populated in the database

  Scenario: Inbox photos start with state "received"
    Given the database is empty
    And a local directory with photos "photo1.jpg"
    When the processor runs for bucket "photo-tagging-inbox"
    Then "photo1.jpg" should have state "received" in the database

  Scenario: Photo state becomes "failed" when image processing errors
    Given the database is empty
    And a local directory with a corrupted oversized image "broken.jpg"
    When the processor attempts to process the image and fails
    Then "broken.jpg" should have state "failed" in the database
