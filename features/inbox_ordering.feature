@local
Feature: Inbox ordering by capture time
  Inbox photos are sorted oldest-captured-first using EXIF DateTimeOriginal.
  Photos without EXIF data sort after all dated photos.

  Scenario: Inbox photos are ordered oldest-captured-first
    Given the database is empty
    And an inbox photo "newer.jpg" with captured_at "2024-06-01 12:00:00"
    And an inbox photo "older.jpg" with captured_at "2022-01-01 09:00:00"
    And an inbox photo "middle.jpg" with captured_at "2023-03-15 15:30:00"
    When I list the inbox
    Then the inbox results should be in order "older.jpg, middle.jpg, newer.jpg"

  Scenario: Photos without EXIF sort after dated photos
    Given the database is empty
    And an inbox photo "dated.jpg" with captured_at "2023-01-01 10:00:00"
    And an inbox photo "no_exif.jpg" with no captured_at
    When I list the inbox
    Then the inbox results should be in order "dated.jpg, no_exif.jpg"

  Scenario: Cursor-based pagination preserves capture-time ordering
    Given the database is empty
    And an inbox photo "a.jpg" with captured_at "2022-01-01 10:00:00"
    And an inbox photo "b.jpg" with captured_at "2022-06-01 10:00:00"
    And an inbox photo "c.jpg" with captured_at "2023-01-01 10:00:00"
    And an inbox photo "d.jpg" with captured_at "2023-06-01 10:00:00"
    When I list the inbox with limit 2
    Then the inbox results should be in order "a.jpg, b.jpg"
    And the inbox listing has a next_cursor
    When I list the inbox with the next cursor and limit 2
    Then the inbox results should be in order "c.jpg, d.jpg"
    And the inbox listing has no next_cursor
