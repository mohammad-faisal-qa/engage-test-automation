Feature: Onsite notification frequency capping
  A notification should reach the right people, and should stop reaching them
  once they have seen it enough. The cap exists so a returning visitor is not
  shown the same message on every page.

  Background:
    Given I am signed in as the admin of "acme"

  Scenario: A customer who has not seen the message yet is eligible
    Given an active notification capped at 2 showings per day
    And a customer who has never seen it
    When we ask whether the customer should be shown the notification
    Then the answer is yes

  Scenario Outline: A customer stops being eligible after <cap> showings
    Given an active notification capped at <cap> showings per day
    And a customer who has already seen it <cap> times
    When we ask whether the customer should be shown the notification
    Then the answer is no because they have seen it enough

    Examples:
      | cap |
      | 1   |
      | 3   |

  Scenario: A paused notification is shown to nobody
    Given a paused notification capped at 5 showings per day
    And a customer who has never seen it
    When we ask whether the customer should be shown the notification
    Then the answer is no because the notification is not running
