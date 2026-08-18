Feature: Onsite survey responses
  A survey collects answers from customers and reports what they said. Answers
  that break the survey's own rules are refused, because a summary built from
  nonsense is worse than no summary.

  Background:
    Given I am signed in as the admin of "acme"

  Scenario: A submitted response is counted in the survey's results
    Given a running survey asking for a rating from 1 to 5
    When a customer answers with a rating of 4
    Then the response is recorded
    And the survey reports 1 response with an average rating of 4.0

  Scenario: An answer outside the allowed range is refused
    Given a running survey asking for a rating from 1 to 5
    When a customer answers with a rating of 9
    Then the answer is refused
    And the survey reports no responses

  Scenario: A closed survey collects nothing
    Given a closed survey asking for a rating from 1 to 5
    When a customer answers with a rating of 4
    Then the answer is refused because the survey is not running
    And the survey reports no responses
