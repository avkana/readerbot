"""Custom actions"""
from typing import Dict, Text, Any, List
import logging
from dateutil import parser
from rasa_sdk.interfaces import Action
from rasa_sdk.events import (
    SlotSet,
    EventType,
    ActionExecuted,
    SessionStarted,
    Restarted,
    FollowupAction,
    UserUtteranceReverted,
)
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.parsing import (
    parse_duckling_time_as_interval,
    parse_duckling_time,
    get_entity_details,
    parse_duckling_currency,
)
from actions.profile import create_mock_profile
from actions.api.store import Store

from actions.custom_forms import CustomFormValidationAction

logger = logging.getLogger(__name__)

NEXT_FORM_NAME = {
    "pay_cc": "cc_payment_form",
    "transfer_money": "transfer_money_form",
    "search_transactions": "transaction_search_form",
    "check_earnings": "transaction_search_form",
}

FORM_DESCRIPTION = {
    "cc_payment_form": "credit card payment",
    "transfer_money_form": "money transfer",
    "transaction_search_form": "transaction search",
}

anonymous_profile = {
    "id": "anonymous",
    "name": "anonymous"
}

def get_user_id_from_event(tracker: Tracker) -> Text:
    """Pulls "session_started" event, if available, and 
       returns the userId from the channel's metadata.
       Anonymous user profile ID is returned if channel 
       metadata is not available
    """
    event = tracker.get_last_event_for("session_started")
    if event is not None:
        # Read the channel's metadata.
        metadata = event.get("metadata", {})
        # If "usedId" key is missing, return anonymous ID.
        return metadata.get("userId", anonymous_profile.get("id"))

    return anonymous_profile.get("id")

class ActionSessionStart(Action):
    def name(self) -> Text:
        return "action_session_start"

    @staticmethod
    async def fetch_slots(tracker: Tracker) -> List[EventType]:
        """Add user profile to the slots if it is not set."""

        slots = []

        # Start by copying all the existing slots
        for key in tracker.current_slot_values().keys():
            slots.append(SlotSet(key=key, value=tracker.get_slot(key)))

        user_channel = tracker.get_latest_input_channel()
        sender_id = tracker.sender_id
        user_profile = tracker.get_slot("user_profile")
        user_name = tracker.get_slot("user_name")

        db = Store()

        if user_profile is None:
            id = get_user_id_from_event(tracker)
            if id == anonymous_profile.get("id"):
                user_profile = anonymous_profile

            slots.append(SlotSet(key="user_profile", value=user_profile))

        if user_name is None:
            slots.append(SlotSet(key="user_name", value=user_profile.get("name")))

        return slots

         
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:

        # the session should begin with a `session_started` event
        events = [SessionStarted()]

        # any slots that should be carried over should come after the
        # `session_started` event
        newEvents = await self.fetch_slots(tracker)
        events.extend(newEvents)

        # an `action_listen` should be added at the end as a user message follows
        events.append(ActionExecuted("action_listen"))

        return events

class ActionPayCC(Action):
    """Pay credit card."""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_pay_cc"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Executes the action"""

        slots = {
            "continue_form": None,
            "confirm": None,
            "credit_card": None,
            "account_type": None,
            "amount-of-money": None,
            "time": None,
            "time_formatted": None,
            "start_time": None,
            "end_time": None,
            "start_time_formatted": None,
            "end_time_formatted": None,
            "grain": None,
            "number": None,
        }

        if tracker.get_slot("confirm") == "yes":
            account_balance = float(tracker.get_slot("account_balance"))
            credit_card = tracker.get_slot("credit_card")
            cc_balance = tracker.get_slot("credit_card_balance")
            amount_of_money = float(tracker.get_slot("amount-of-money"))
            amount_transferred = float(tracker.get_slot("amount_transferred"))

            cc_balance[credit_card.lower()]["current balance"] -= amount_of_money
            account_balance = account_balance - amount_of_money
            dispatcher.utter_message(template="utter_cc_pay_scheduled")

            slots["amount_transferred"] = amount_transferred + amount_of_money
            slots["account_balance"] = f"{account_balance:.2f}"
            slots["credit_card_balance"] = cc_balance
        else:
            dispatcher.utter_message(template="utter_cc_pay_cancelled")

        return [SlotSet(slot, value) for slot, value in slots.items()]


class ValidatePayCCForm(CustomFormValidationAction):
    """Validates Slots of the cc_payment_form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_cc_payment_form"

    async def validate_amount_of_money(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'amount-of-money' slot"""
        credit_card = tracker.get_slot("credit_card")
        cc_balance = tracker.get_slot("credit_card_balance")
        account_balance = float(tracker.get_slot("account_balance"))
        try:
            entity = get_entity_details(
                tracker, "amount-of-money"
            ) or get_entity_details(tracker, "number")
            amount_currency = parse_duckling_currency(entity)
            if not amount_currency:
                raise TypeError
            if account_balance < float(amount_currency.get("amount-of-money")):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"amount-of-money": None}
            return amount_currency
        except (TypeError, AttributeError):
            pass
        # check if user asked to pay the full or the minimum balance
        if value and value.lower() in cc_balance.get(credit_card.lower()):
            key = value.lower()
            amount = cc_balance.get(credit_card.lower()).get(key)
            amount_type = f" (your {key})"

            if account_balance < float(amount):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"amount-of-money": None}
            return {
                "amount-of-money": f"{amount:.2f}",
                "payment_amount_type": amount_type,
                "currency": "$",
            }

        dispatcher.utter_message(template="utter_no_payment_amount")
        return {"amount-of-money": None}

    async def validate_credit_card(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'credit_card' slot"""
        cc_balance = tracker.get_slot("credit_card_balance")
        if value and value.lower() in list(cc_balance.keys()):
            return {"credit_card": value.title()}

        dispatcher.utter_message(template="utter_no_creditcard")
        return {"credit_card": None}

    async def explain_credit_card(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Explains 'credit_card' slot"""
        dispatcher.utter_message("You have the following credits cards:")
        credit_card_balance = tracker.get_slot("credit_card_balance")
        for credit_card in credit_card_balance.keys():
            current_balance = credit_card_balance[credit_card]["current balance"]
            dispatcher.utter_message(
                template="utter_credit_card_balance",
                **{
                    "credit_card": credit_card.title(),
                    "amount-of-money": f"{current_balance:.2f}",
                },
            )
        return {}

    async def validate_time(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'time' slot"""
        timeentity = get_entity_details(tracker, "time")
        parsedtime = timeentity and parse_duckling_time(timeentity)
        if not parsedtime:
            dispatcher.utter_message(template="utter_no_transactdate")
            return {"time": None}
        return parsedtime

    async def validate_confirm(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'confirm' slot"""
        if value in ["yes", "no"]:
            return {"confirm": value}

        return {"confirm": None}


class ActionTransactionSearch(Action):
    """Searches for a transaction"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_transaction_search"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Executes the action"""
        slots = {
            "continue_form": None,
            "confirm": None,
            "time": None,
            "time_formatted": None,
            "start_time": None,
            "end_time": None,
            "start_time_formatted": None,
            "end_time_formatted": None,
            "grain": None,
            "search_type": None,
            "vendor_name": None,
        }

        if tracker.get_slot("confirm") == "yes":
            search_type = tracker.get_slot("search_type")
            transaction_history = tracker.get_slot("transaction_history")
            transactions_subset = transaction_history.get(search_type, {})
            vendor_name = tracker.get_slot("vendor_name")

            if vendor_name:
                transactions = transactions_subset.get(vendor_name.lower())
                vendor_name = f" with {vendor_name}"
            else:
                transactions = [
                    v for k in list(transactions_subset.values()) for v in k
                ]
                vendor_name = ""

            start_time = parser.isoparse(tracker.get_slot("start_time"))
            end_time = parser.isoparse(tracker.get_slot("end_time"))

            for i in range(len(transactions) - 1, -1, -1):
                transaction = transactions[i]
                transaction_date = parser.isoparse(transaction.get("date"))

                if transaction_date < start_time or transaction_date > end_time:
                    transactions.pop(i)

            numtransacts = len(transactions)
            total = sum([t.get("amount") for t in transactions])
            slotvars = {
                "total": f"{total:.2f}",
                "numtransacts": numtransacts,
                "start_time_formatted": tracker.get_slot("start_time_formatted"),
                "end_time_formatted": tracker.get_slot("end_time_formatted"),
                "vendor_name": vendor_name,
            }

            dispatcher.utter_message(
                template=f"utter_searching_{search_type}_transactions",
                **slotvars,
            )
            dispatcher.utter_message(
                template=f"utter_found_{search_type}_transactions", **slotvars
            )
        else:
            dispatcher.utter_message(template="utter_transaction_search_cancelled")

        return [SlotSet(slot, value) for slot, value in slots.items()]


class ValidateTransactionSearchForm(CustomFormValidationAction):
    """Validates Slots of the transaction_search_form"""

    def name(self) -> Text:
        """Unique identifier of the form"""
        return "validate_transaction_search_form"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Custom validates the filled slots"""
        events = await super().run(dispatcher, tracker, domain)

        # For 'spend' type transactions we need to know the vendor_name
        search_type = tracker.get_slot("search_type")
        if search_type == "spend":
            vendor_name = tracker.get_slot("vendor_name")
            if not vendor_name:
                events.append(SlotSet("requested_slot", "vendor_name"))

        return events

    async def validate_search_type(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'search_type' slot"""
        if value in ["spend", "deposit"]:
            return {"search_type": value}

        return {"search_type": None}

    async def validate_vendor_name(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'vendor_name' slot"""
        if value and value.lower() in tracker.get_slot("vendor_list"):
            return {"vendor_name": value}

        dispatcher.utter_message(template="utter_no_vendor_name")
        return {"vendor_name": None}

    async def validate_time(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'time' slot"""
        timeentity = get_entity_details(tracker, "time")
        parsedinterval = timeentity and parse_duckling_time_as_interval(timeentity)
        if not parsedinterval:
            dispatcher.utter_message(template="utter_no_transactdate")
            return {"time": None}

        return parsedinterval


class ActionTransferMoney(Action):
    """Transfers Money."""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_transfer_money"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the action"""
        slots = {
            "continue_form": None,
            "confirm": None,
            "PERSON": None,
            "amount-of-money": None,
            "number": None,
        }

        if tracker.get_slot("confirm") == "yes":
            amount_of_money = float(tracker.get_slot("amount-of-money"))
            account_balance = float(tracker.get_slot("account_balance"))

            updated_account_balance = account_balance - amount_of_money

            dispatcher.utter_message(template="utter_transfer_complete")

            amount_transferred = float(tracker.get_slot("amount_transferred"))
            slots["amount_transferred"] = amount_transferred + amount_of_money
            slots["account_balance"] = f"{updated_account_balance:.2f}"
        else:
            dispatcher.utter_message(template="utter_transfer_cancelled")

        return [SlotSet(slot, value) for slot, value in slots.items()]


class ValidateTransferMoneyForm(CustomFormValidationAction):
    """Validates Slots of the transfer_money_form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_transfer_money_form"

    async def validate_PERSON(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'PERSON' slot"""
        # It is possible that both Spacy & DIET extracted the PERSON
        # Just pick the first one
        if isinstance(value, list):
            value = value[0]

        name = value.title() if value else None
        known_recipients = tracker.get_slot("known_recipients")
        first_names = [name.split()[0] for name in known_recipients]
        if name in known_recipients:
            return {"PERSON": name}

        if name in first_names:
            index = first_names.index(name)
            fullname = known_recipients[index]
            return {"PERSON": fullname}

        dispatcher.utter_message(template="utter_unknown_recipient", PERSON=value)
        return {"PERSON": None}

    async def explain_PERSON(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Explains 'PERSON' slot"""
        recipients = tracker.get_slot("known_recipients")
        formatted_recipients = "\n" + "\n".join(
            [f"- {recipient}" for recipient in recipients]
        )
        dispatcher.utter_message(
            template="utter_recipients",
            formatted_recipients=formatted_recipients,
        )
        return {}

    async def validate_amount_of_money(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'amount-of-money' slot"""
        account_balance = float(tracker.get_slot("account_balance"))
        try:
            entity = get_entity_details(
                tracker, "amount-of-money"
            ) or get_entity_details(tracker, "number")
            amount_currency = parse_duckling_currency(entity)
            if not amount_currency:
                raise TypeError
            if account_balance < float(amount_currency.get("amount-of-money")):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"amount-of-money": None}
            return amount_currency
        except (TypeError, AttributeError):
            dispatcher.utter_message(template="utter_no_payment_amount")
            return {"amount-of-money": None}

    async def validate_confirm(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'confirm' slot"""
        if value in ["yes", "no"]:
            return {"confirm": value}

        return {"confirm": None}


class ActionShowBalance(Action):
    """Shows the balance of bank or credit card accounts"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_show_balance"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        account_type = tracker.get_slot("account_type")

        if account_type == "credit":
            # show credit card balance
            credit_card_balance = tracker.get_slot("credit_card_balance")
            credit_card = tracker.get_slot("credit_card")

            if credit_card and credit_card.lower() in credit_card_balance:
                current_balance = credit_card_balance[credit_card.lower()][
                    "current balance"
                ]
                dispatcher.utter_message(
                    template="utter_credit_card_balance",
                    **{
                        "credit_card": credit_card.title(),
                        "amount-of-money": f"{current_balance:.2f}",
                    },
                )
            else:
                for credit_card in credit_card_balance.keys():
                    current_balance = credit_card_balance[credit_card][
                        "current balance"
                    ]
                    dispatcher.utter_message(
                        template="utter_credit_card_balance",
                        **{
                            "credit_card": credit_card.title(),
                            "amount-of-money": f"{current_balance:.2f}",
                        },
                    )
        else:
            # show bank account balance
            account_balance = float(tracker.get_slot("account_balance"))
            amount = tracker.get_slot("amount_transferred")
            if amount:
                amount = float(tracker.get_slot("amount_transferred"))
                init_account_balance = account_balance + amount
                dispatcher.utter_message(
                    template="utter_changed_account_balance",
                    init_account_balance=f"{init_account_balance:.2f}",
                    account_balance=f"{account_balance:.2f}",
                )
            else:
                dispatcher.utter_message(
                    template="utter_account_balance",
                    init_account_balance=f"{account_balance:.2f}",
                )

        events = []
        active_form_name = tracker.active_form.get("name")
        if active_form_name:
            # keep the tracker clean for the predictions with form switch stories
            events.append(UserUtteranceReverted())
            # trigger utter_ask_{form}_continue_form, by making it the requested_slot
            events.append(SlotSet("continue_form", None))
            # avoid that bot goes in listen mode after UserUtteranceReverted
            events.append(FollowupAction(active_form_name))

        return events


class ActionShowRecipients(Action):
    """Lists the contents of then known_recipients slot"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_show_recipients"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        recipients = tracker.get_slot("known_recipients")
        formatted_recipients = "\n" + "\n".join(
            [f"- {recipient}" for recipient in recipients]
        )
        dispatcher.utter_message(
            template="utter_recipients",
            formatted_recipients=formatted_recipients,
        )

        events = []
        active_form_name = tracker.active_form.get("name")
        if active_form_name:
            # keep the tracker clean for the predictions with form switch stories
            events.append(UserUtteranceReverted())
            # trigger utter_ask_{form}_continue_form, by making it the requested_slot
            events.append(SlotSet("continue_form", None))
            # # avoid that bot goes in listen mode after UserUtteranceReverted
            events.append(FollowupAction(active_form_name))

        return events


class ActionShowTransferCharge(Action):
    """Lists the transfer charges"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_show_transfer_charge"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        dispatcher.utter_message(template="utter_transfer_charge")

        events = []
        active_form_name = tracker.active_form.get("name")
        if active_form_name:
            # keep the tracker clean for the predictions with form switch stories
            events.append(UserUtteranceReverted())
            # trigger utter_ask_{form}_continue_form, by making it the requested_slot
            events.append(SlotSet("continue_form", None))
            # # avoid that bot goes in listen mode after UserUtteranceReverted
            events.append(FollowupAction(active_form_name))

        return events


class ActionRestart(Action):
    """Executes after restart of a session"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_restart"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:
        """Executes the custom action"""
        return [Restarted(), FollowupAction("action_session_start")]


class ActionAskTransactionSearchFormConfirm(Action):
    """Asks for the 'confirm' slot of 'transaction_search_form'

    A custom action is used instead of an 'utter_ask' response because a different
    question is asked based on 'search_type' and 'vendor_name' slots.
    """

    def name(self) -> Text:
        return "action_ask_transaction_search_form_confirm"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        search_type = tracker.get_slot("search_type")
        vendor_name = tracker.get_slot("vendor_name")
        start_time_formatted = tracker.get_slot("start_time_formatted")
        end_time_formatted = tracker.get_slot("end_time_formatted")

        if vendor_name:
            vendor_name = f" with {vendor_name}"
        else:
            vendor_name = ""

        if search_type == "spend":
            text = (
                f"Do you want to search for transactions{vendor_name} between "
                f"{start_time_formatted} and {end_time_formatted}?"
            )
        elif search_type == "deposit":
            text = (
                f"Do you want to search deposits made to your account between "
                f"{start_time_formatted} and {end_time_formatted}?"
            )

        buttons = [
            {"payload": "/affirm", "title": "Yes"},
            {"payload": "/deny", "title": "No"},
        ]

        dispatcher.utter_message(text=text, buttons=buttons)

        return []


class ActionSwitchFormsAsk(Action):
    """Asks to switch forms"""

    def name(self) -> Text:
        return "action_switch_forms_ask"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        active_form_name = tracker.active_form.get("name")
        intent_name = tracker.latest_message["intent"]["name"]
        next_form_name = NEXT_FORM_NAME.get(intent_name)

        if (
            active_form_name not in FORM_DESCRIPTION.keys()
            or next_form_name not in FORM_DESCRIPTION.keys()
        ):
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}` & "
                f"`next_form_name={next_form_name}`"
            )
            next_form_name = None
        else:
            text = (
                f"We haven't completed the {FORM_DESCRIPTION[active_form_name]} yet. "
                f"Are you sure you want to switch to {FORM_DESCRIPTION[next_form_name]}?"
            )
            buttons = [
                {"payload": "/affirm", "title": "Yes"},
                {"payload": "/deny", "title": "No"},
            ]
            dispatcher.utter_message(text=text, buttons=buttons)

        return [SlotSet("next_form_name", next_form_name)]


class ActionSwitchFormsDeny(Action):
    """Does not switch forms"""

    def name(self) -> Text:
        return "action_switch_forms_deny"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        active_form_name = tracker.active_form.get("name")

        if active_form_name not in FORM_DESCRIPTION.keys():
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}`."
            )
        else:
            text = f"Ok, let's continue with the {FORM_DESCRIPTION[active_form_name]}."
            dispatcher.utter_message(text=text)

        return [SlotSet("next_form_name", None)]


class ActionSwitchFormsAffirm(Action):
    """Switches forms"""

    def name(self) -> Text:
        return "action_switch_forms_affirm"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        active_form_name = tracker.active_form.get("name")
        next_form_name = tracker.get_slot("next_form_name")

        if (
            active_form_name not in FORM_DESCRIPTION.keys()
            or next_form_name not in FORM_DESCRIPTION.keys()
        ):
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}` & "
                f"`next_form_name={next_form_name}`"
            )
        else:
            text = (
                f"Great. Let's switch from the {FORM_DESCRIPTION[active_form_name]} "
                f"to {FORM_DESCRIPTION[next_form_name]}. "
                f"Once completed, you will have the option to switch back."
            )
            dispatcher.utter_message(text=text)

        return [
            SlotSet("previous_form_name", active_form_name),
            SlotSet("next_form_name", None),
        ]


class ActionSwitchBackAsk(Action):
    """Asks to switch back to previous form"""

    def name(self) -> Text:
        return "action_switch_back_ask"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        previous_form_name = tracker.get_slot("previous_form_name")

        if previous_form_name not in FORM_DESCRIPTION.keys():
            logger.debug(
                f"Cannot create text for `previous_form_name={previous_form_name}`"
            )
            previous_form_name = None
        else:
            text = (
                f"Would you like to go back to the "
                f"{FORM_DESCRIPTION[previous_form_name]} now?."
            )
            buttons = [
                {"payload": "/affirm", "title": "Yes"},
                {"payload": "/deny", "title": "No"},
            ]
            dispatcher.utter_message(text=text, buttons=buttons)

        return [SlotSet("previous_form_name", None)]
