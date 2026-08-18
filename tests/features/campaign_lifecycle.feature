Feature: Campaign lifecycle
  A campaign is created against an audience, sent, and reports on what happened.
  Nothing here mentions a screen or a button: these are the outcomes a marketing
  manager would recognise, and they stay true however the product is operated.

  Background:
    Given I am signed in as the admin of "acme"

  Scenario: A campaign reaches everyone in its segment
    Given a segment containing 3 customers
    And a campaign targeting that segment
    When the campaign is sent
    Then every customer in the segment receives it
    And the campaign is recorded as sent

  Scenario: A campaign cannot be reported as sent without being sent
    Given a segment containing 2 customers
    And a campaign targeting that segment
    When someone tries to mark the campaign as sent without sending it
    Then the campaign is refused
    And the campaign is still a draft

  Scenario: A campaign with no audience is not sent
    Given a segment containing no customers
    And a campaign targeting that segment
    When the campaign is sent
    Then the send is refused because there is nobody to send to
    And nobody receives it

  Scenario: Delivery outcomes are reflected in the campaign's results
    Given a segment containing 2 customers
    And a campaign targeting that segment
    When the campaign is sent
    And the provider reports that 2 were delivered and 1 was opened
    Then the campaign reports 2 delivered and 1 opened
    And the results never show more opens than deliveries
