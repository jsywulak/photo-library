@infrastructure
Feature: photo_events audit log written by deployed Lambdas
  Each Lambda records its actions in the photo_events table so the system
  is debuggable, recoverable, and auditable.

  Scenario: Inbox Lambda writes a "promoted" event when a photo is processed
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And a photo_events row with event_type "promoted" and actor "inbox" should exist in Neon for the inbox photo

  Scenario: Inbox Lambda writes an "archived" event when an inbox photo is archived
    Given the inbox Lambda is deployed
    And a photo is uploaded to the inbox bucket and recorded in the database v2
    When the inbox Function URL POST /archive-inbox is called for the inbox photo with the correct API key
    Then the HTTP response status should be 200 v2
    And a photo_events row with event_type "archived" and actor "inbox" should exist in Neon for the inbox photo

  Scenario: Searcher writes a "tag_added" event for each tag added
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "animal"
    When the Function URL POST /add-tags is called for the photo with tags "wire, cozy" and the correct API key
    Then the HTTP response status should be 200
    And a photo_events row with event_type "tag_added" and actor "searcher" should exist in Neon for the seeded photo with tag "wire" in details
    And a photo_events row with event_type "tag_added" and actor "searcher" should exist in Neon for the seeded photo with tag "cozy" in details

  Scenario: Searcher writes a "tag_removed" event when a tag is removed
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "cat, animal"
    When the Function URL POST /remove-tag is called for the photo with tag "cat" and the correct API key
    Then the HTTP response status should be 200
    And a photo_events row with event_type "tag_removed" and actor "searcher" should exist in Neon for the seeded photo with tag "cat" in details

  Scenario: Searcher writes an "archived" event when a photo is archived
    Given the searcher Lambda is deployed
    And a photo exists in the Neon database tagged with "archive-test"
    When the Function URL POST /archive is called for the photo with the correct API key
    Then the HTTP response status should be 200
    And a photo_events row with event_type "archived" and actor "searcher" should exist in Neon for the seeded photo

  Scenario: Image handler writes a "received" event for the inbox photo
    Given the image handler Lambda is deployed
    And a test photo is uploaded to the upload bucket
    When the image handler Lambda processes the photo
    Then a photo_events row with event_type "received" and actor "image_handler" should exist in Neon for the inbox key

  Scenario: Thumbnailer writes a "thumbnail_created" event when a thumbnail is generated
    Given the thumbnailer Lambda is deployed
    And a test photo is uploaded to the photos bucket
    When the thumbnailer Lambda processes the photo
    Then a photo_events row with event_type "thumbnail_created" and actor "thumbnailer" should exist in Neon for the photo

  Scenario: Thumbnailer writes a "thumbnail_skipped" event when the thumbnail already exists
    Given the thumbnailer Lambda is deployed
    And a test photo is uploaded to the photos bucket
    And a thumbnail already exists for the photo
    When the thumbnailer Lambda processes the photo
    Then a photo_events row with event_type "thumbnail_skipped" and actor "thumbnailer" should exist in Neon for the photo
