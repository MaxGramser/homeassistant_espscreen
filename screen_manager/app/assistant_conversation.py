"""Shared text-turn orchestration, independent of Claude's wire format.

Native Realtime audio drives its own turns, using the same instructions, context
and server tool dispatcher. It does not pass through this text-only transport.
"""
import json

from assistant_tools import prompt, TOOLS, completed_command


class Conversation:
    def __init__(self, provider, http, key, model):
        self.provider, self.http, self.key, self.model = provider, http, key, model
        self.turns = []

    async def reply(self, text, context, dispatch):
        # Drop complete turns only, never orphan tool results. Histories are
        # private, memory-only, bounded, and removed with the voice session.
        history = [message for turn in self.turns[-6:] for message in turn]
        turn = [{'role': 'user', 'content': text}]
        sources, action, end_voice = {}, False, False
        instructions = prompt(context)
        for _ in range(8):
            result = await self.provider.respond(self.http, self.key, model=self.model,
                instructions=instructions, tools=TOOLS, messages=history + turn)
            turn.append(result['message'])
            if not result['calls']:
                answer = result['text']
                if not answer or len(answer) > 12000:
                    raise ValueError('The assistant returned no complete spoken reply.')
                self.remember(turn)
                return {'text': answer, 'sources': list(sources.values()), 'action': action,
                        **({'end_voice': True} if end_voice else {})}
            if len(result['calls']) > 8:
                raise ValueError('The assistant requested too many actions.')
            outputs = []
            for call in result['calls']:
                output = await dispatch(call['id'], call['name'], call['arguments'])
                outputs.append((call['id'], output))
                if output.get('end_voice_immediately') is True:
                    # No further provider turn, device action or TTS after a
                    # spoken stop. This session's history will be discarded.
                    return {'text': '', 'sources': [], 'action': action,
                            'end_voice': True, 'end_voice_immediately': True}
                if call['name'] == 'lookup_current_information' and output.get('status') == 'ok':
                    sources.update((s['url'], s) for s in output.get('sources', []))
                action |= output.get('status') == 'accepted'
                end_voice |= output.get('end_voice') is True
            turn.append(self.provider.tool_results(outputs))
            if completed_command([output for _, output in outputs]):
                self.remember(turn)
                return {'text': '', 'sources': [], 'action': action, 'complete_request': True,
                        **({'end_voice': True} if end_voice else {})}
            if all(call['name'] == 'wait_for_user' and output.get('wait_for_user') is True
                   for call, (_, output) in zip(result['calls'], outputs)):
                self.remember(turn)
                return {'text': '', 'sources': [], 'action': False, 'wait_for_user': True}
        # Never automatically replay a partly executed turn after provider errors.
        raise ValueError('The assistant reached the tool limit. Check device state before trying again.')

    def remember(self, turn):
        self.turns.append(turn)
        while len(self.turns) > 6 or len(json.dumps(self.turns)) > 128000:
            self.turns.pop(0)
