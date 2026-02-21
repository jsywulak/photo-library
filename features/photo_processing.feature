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
