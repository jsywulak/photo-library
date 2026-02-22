Feature: Photo search by tags
  Searching returns photos that match any of the given tags,
  ranked by how many of the searched tags each photo has,
  with photos that match none of the tags excluded entirely.

  Scenario: No photos match any searched tag
    Given the database is empty
    And a photo "sunset.jpg" tagged with "landscape, sky"
    When I search for "cat, dog"
    Then the results should be empty

  Scenario: Photos matching any searched tag are returned
    Given the database is empty
    And a photo "cat.jpg" tagged with "cat, indoor"
    And a photo "dog.jpg" tagged with "dog, outdoor"
    And a photo "tree.jpg" tagged with "nature, outdoor"
    When I search for "cat, dog"
    Then the results should contain "cat.jpg"
    And the results should contain "dog.jpg"
    And the results should not contain "tree.jpg"

  Scenario: Photos with more tag matches rank higher
    Given the database is empty
    And a photo "best.jpg" tagged with "cat, animal, indoor"
    And a photo "partial.jpg" tagged with "cat, outdoor"
    When I search for "cat, animal, indoor"
    Then "best.jpg" should rank above "partial.jpg"

  Scenario: Photos with no matching tags are excluded
    Given the database is empty
    And a photo "cat.jpg" tagged with "cat, animal"
    And a photo "landscape.jpg" tagged with "mountain, sky"
    When I search for "cat"
    Then the results should contain "cat.jpg"
    And the results should not contain "landscape.jpg"
