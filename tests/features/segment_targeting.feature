Feature: Segment targeting
  A segment is a rule about customers, and membership is worked out when it is
  asked for rather than stored. The interesting property is that a rule may name
  something recorded about the customer directly, or something held among their
  attributes — and a marketer should not have to know which is which.

  Background:
    Given I am signed in as the admin of "acme"

  Scenario Outline: Customers are selected by <description>
    Given a customer whose <field> is "<matching>"
    And a customer whose <field> is "<other>"
    When a segment selects customers whose <field> is "<matching>"
    Then only the first customer is in the segment

    Examples:
      | description             | field          | matching   | other |
      | their plan              | plan           | enterprise | free  |
      | a recorded attribute    | lifetime_value | 9000       | 10    |

  Scenario: A segment with no rules selects nobody
    Given a customer whose plan is "pro"
    When a segment is created with no rules at all
    Then the segment contains nobody
