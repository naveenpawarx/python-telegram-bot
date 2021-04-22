#!/usr/bin/env python
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2021
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
import time
from copy import deepcopy
from datetime import datetime

import pytest
import pytz

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, User
from telegram.ext.callbackdatacache import (
    CallbackDataCache,
    KeyboardData,
    InvalidCallbackData,
)


@pytest.fixture(scope='function')
def callback_data_cache(bot):
    return CallbackDataCache(bot)


class TestCallbackDataCache:
    @pytest.mark.parametrize('maxsize', [1, 5, 2048])
    def test_init_maxsize(self, maxsize, bot):
        assert CallbackDataCache(bot).maxsize == 1024
        cdc = CallbackDataCache(bot, maxsize=maxsize)
        assert cdc.maxsize == maxsize
        assert cdc.bot is bot

    def test_init_and_access__persistent_data(self, bot):
        keyboard_data = KeyboardData('123', 456, {'button': 678})
        persistent_data = ([keyboard_data.to_tuple()], {'id': '123'})
        cdc = CallbackDataCache(bot, persistent_data=persistent_data)

        assert cdc.maxsize == 1024
        assert dict(cdc._callback_queries) == {'id': '123'}
        assert list(cdc._keyboard_data.keys()) == ['123']
        assert cdc._keyboard_data['123'].keyboard_uuid == '123'
        assert cdc._keyboard_data['123'].access_time == 456
        assert cdc._keyboard_data['123'].button_data == {'button': 678}

        assert cdc.persistence_data == persistent_data

    def test_process_keyboard(self, callback_data_cache):
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        non_changing_button = InlineKeyboardButton('non-changing', url='https://ptb.org')
        reply_markup = InlineKeyboardMarkup.from_row(
            [non_changing_button, changing_button_1, changing_button_2]
        )

        out = callback_data_cache.process_keyboard(reply_markup)
        assert out.inline_keyboard[0][0] is non_changing_button
        assert out.inline_keyboard[0][1] != changing_button_1
        assert out.inline_keyboard[0][2] != changing_button_2

        keyboard_1, button_1 = callback_data_cache.extract_uuids(
            out.inline_keyboard[0][1].callback_data
        )
        keyboard_2, button_2 = callback_data_cache.extract_uuids(
            out.inline_keyboard[0][2].callback_data
        )
        assert keyboard_1 == keyboard_2
        assert (
            callback_data_cache._keyboard_data[keyboard_1].button_data[button_1] == 'some data 1'
        )
        assert (
            callback_data_cache._keyboard_data[keyboard_2].button_data[button_2] == 'some data 2'
        )

    def test_process_keyboard_no_changing_button(self, callback_data_cache):
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton('non-changing', url='https://ptb.org')
        )
        assert callback_data_cache.process_keyboard(reply_markup) is reply_markup

    def test_process_keyboard_full(self, bot):
        cdc = CallbackDataCache(bot, maxsize=1)
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        non_changing_button = InlineKeyboardButton('non-changing', url='https://ptb.org')
        reply_markup = InlineKeyboardMarkup.from_row(
            [non_changing_button, changing_button_1, changing_button_2]
        )

        out1 = cdc.process_keyboard(reply_markup)
        assert len(cdc.persistence_data[0]) == 1
        out2 = cdc.process_keyboard(reply_markup)
        assert len(cdc.persistence_data[0]) == 1

        keyboard_1, button_1 = cdc.extract_uuids(out1.inline_keyboard[0][1].callback_data)
        keyboard_2, button_2 = cdc.extract_uuids(out2.inline_keyboard[0][2].callback_data)
        assert cdc.persistence_data[0][0][0] != keyboard_1
        assert cdc.persistence_data[0][0][0] == keyboard_2

    @pytest.mark.parametrize('data', [True, False])
    @pytest.mark.parametrize('message', [True, False])
    @pytest.mark.parametrize('invalid', [True, False])
    def test_process_callback_query(self, callback_data_cache, data, message, invalid):
        """This also tests large parts of process_message"""
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        non_changing_button = InlineKeyboardButton('non-changing', url='https://ptb.org')
        reply_markup = InlineKeyboardMarkup.from_row(
            [non_changing_button, changing_button_1, changing_button_2]
        )

        out = callback_data_cache.process_keyboard(reply_markup)
        if invalid:
            callback_data_cache.clear_callback_data()

        effective_message = Message(message_id=1, date=None, chat=None, reply_markup=out)
        effective_message.reply_to_message = deepcopy(effective_message)
        effective_message.pinned_message = deepcopy(effective_message)
        callback_query = CallbackQuery(
            '1',
            from_user=None,
            chat_instance=None,
            data=out.inline_keyboard[0][1].callback_data if data else None,
            message=effective_message if message else None,
        )
        result = callback_data_cache.process_callback_query(callback_query)

        if not invalid:
            if data:
                assert result.data == 'some data 1'
            else:
                assert result.data is None
            if message:
                for msg in (
                    result.message,
                    result.message.reply_to_message,
                    result.message.pinned_message,
                ):
                    assert msg.reply_markup == reply_markup
        else:
            if data:
                assert isinstance(result.data, InvalidCallbackData)
            else:
                assert result.data is None
            if message:
                for msg in (
                    result.message,
                    result.message.reply_to_message,
                    result.message.pinned_message,
                ):
                    assert isinstance(
                        msg.reply_markup.inline_keyboard[0][1].callback_data,
                        InvalidCallbackData,
                    )
                    assert isinstance(
                        msg.reply_markup.inline_keyboard[0][2].callback_data,
                        InvalidCallbackData,
                    )

    @pytest.mark.parametrize('pass_from_user', [True, False])
    @pytest.mark.parametrize('pass_via_bot', [True, False])
    def test_process_message_wrong_sender(self, pass_from_user, pass_via_bot, callback_data_cache):
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton('test', callback_data='callback_data')
        )
        user = User(1, 'first', False)
        message = Message(
            1,
            None,
            None,
            from_user=user if pass_from_user else None,
            via_bot=user if pass_via_bot else None,
            reply_markup=reply_markup,
        )
        result = callback_data_cache.process_message(message)
        if pass_from_user or pass_via_bot:
            # Here we can determine that the message is not from our bot, so no replacing
            assert result.reply_markup.inline_keyboard[0][0].callback_data == 'callback_data'
        else:
            # Here we have no chance to know, so InvalidCallbackData
            assert isinstance(
                result.reply_markup.inline_keyboard[0][0].callback_data, InvalidCallbackData
            )

    @pytest.mark.parametrize('pass_from_user', [True, False])
    def test_process_message_inline_mode(self, pass_from_user, callback_data_cache):
        """Check that via_bot tells us correctly that our bot sent the message, even if
        from_user is not our bot."""
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton('test', callback_data='callback_data')
        )
        user = User(1, 'first', False)
        message = Message(
            1,
            None,
            None,
            from_user=user if pass_from_user else None,
            via_bot=callback_data_cache.bot.bot,
            reply_markup=callback_data_cache.process_keyboard(reply_markup),
        )
        result = callback_data_cache.process_message(message)
        # Here we can determine that the message is not from our bot, so no replacing
        assert result.reply_markup.inline_keyboard[0][0].callback_data == 'callback_data'

    def test_process_message_no_reply_markup(self, callback_data_cache):
        message = Message(1, None, None)
        result = callback_data_cache.process_message(message)
        assert result.reply_markup is None

    def test_drop_data(self, callback_data_cache):
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        reply_markup = InlineKeyboardMarkup.from_row([changing_button_1, changing_button_2])

        out = callback_data_cache.process_keyboard(reply_markup)
        callback_query = CallbackQuery(
            '1',
            from_user=None,
            chat_instance=None,
            data=out.inline_keyboard[0][1].callback_data,
        )
        callback_data_cache.process_callback_query(callback_query)

        assert len(callback_data_cache.persistence_data[1]) == 1
        assert len(callback_data_cache.persistence_data[0]) == 1

        callback_data_cache.drop_data(callback_query)
        assert len(callback_data_cache.persistence_data[1]) == 0
        assert len(callback_data_cache.persistence_data[0]) == 0

    def test_drop_data_missing_data(self, callback_data_cache):
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        reply_markup = InlineKeyboardMarkup.from_row([changing_button_1, changing_button_2])

        out = callback_data_cache.process_keyboard(reply_markup)
        callback_query = CallbackQuery(
            '1',
            from_user=None,
            chat_instance=None,
            data=out.inline_keyboard[0][1].callback_data,
        )

        with pytest.raises(KeyError, match='CallbackQuery was not found in cache.'):
            callback_data_cache.drop_data(callback_query)

        callback_data_cache.process_callback_query(callback_query)
        callback_data_cache.clear_callback_data()
        callback_data_cache.drop_data(callback_query)
        assert callback_data_cache.persistence_data == ([], {})

    @pytest.mark.parametrize('method', ('callback_data', 'callback_queries'))
    def test_clear_all(self, callback_data_cache, method):
        changing_button_1 = InlineKeyboardButton('changing', callback_data='some data 1')
        changing_button_2 = InlineKeyboardButton('changing', callback_data='some data 2')
        reply_markup = InlineKeyboardMarkup.from_row([changing_button_1, changing_button_2])

        for i in range(100):
            out = callback_data_cache.process_keyboard(reply_markup)
            callback_query = CallbackQuery(
                str(i),
                from_user=None,
                chat_instance=None,
                data=out.inline_keyboard[0][1].callback_data,
            )
            callback_data_cache.process_callback_query(callback_query)

        if method == 'callback_data':
            callback_data_cache.clear_callback_data()
            assert len(callback_data_cache.persistence_data[0]) == 0
            assert len(callback_data_cache.persistence_data[1]) == 100
        else:
            callback_data_cache.clear_callback_queries()
            assert len(callback_data_cache.persistence_data[0]) == 100
            assert len(callback_data_cache.persistence_data[1]) == 0

    @pytest.mark.parametrize('time_method', ['time', 'datetime', 'defaults'])
    def test_clear_cutoff(self, callback_data_cache, time_method, tz_bot):
        for i in range(50):
            reply_markup = InlineKeyboardMarkup.from_button(
                InlineKeyboardButton('changing', callback_data=str(i))
            )
            out = callback_data_cache.process_keyboard(reply_markup)
            callback_query = CallbackQuery(
                str(i),
                from_user=None,
                chat_instance=None,
                data=out.inline_keyboard[0][0].callback_data,
            )
            callback_data_cache.process_callback_query(callback_query)

        time.sleep(0.1)
        if time_method == 'time':
            cutoff = time.time()
        elif time_method == 'datetime':
            cutoff = datetime.now(pytz.utc)
        else:
            cutoff = datetime.now(tz_bot.defaults.tzinfo).replace(tzinfo=None)
            callback_data_cache.bot = tz_bot
        time.sleep(0.1)

        for i in range(50, 100):
            reply_markup = InlineKeyboardMarkup.from_button(
                InlineKeyboardButton('changing', callback_data=str(i))
            )
            out = callback_data_cache.process_keyboard(reply_markup)
            callback_query = CallbackQuery(
                str(i),
                from_user=None,
                chat_instance=None,
                data=out.inline_keyboard[0][0].callback_data,
            )
            callback_data_cache.process_callback_query(callback_query)

        callback_data_cache.clear_callback_data(time_cutoff=cutoff)
        assert len(callback_data_cache.persistence_data[0]) == 50
        assert len(callback_data_cache.persistence_data[1]) == 100
        callback_data = [
            list(data[2].values())[0] for data in callback_data_cache.persistence_data[0]
        ]
        assert callback_data == list(str(i) for i in range(50, 100))