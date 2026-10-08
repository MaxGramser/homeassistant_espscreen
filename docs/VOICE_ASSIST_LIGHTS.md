# Assist light and switch control experiment

The voice settings offer two routes for explicit light/switch on/off and light brightness commands:
**Tessera → Home Assistant** (the existing default) and **Home Assistant Assist**.
The second route calls Home Assistant's built-in Assist tools through its official
MCP Server integration. OpenAI keeps direct audio; Claude keeps HA speech-to-text
and text-to-speech. No second conversation agent or model is invoked for an action.

## HA-managed Assist versus direct OpenAI audio

These are different ways to handle a spoken request:

| Route | Speech and conversation handling |
| --- | --- |
| Full HA Assist pipeline | Panel audio goes through the selected speech-to-text service. The selected HA conversation agent interprets the text and returns an answer, which the chosen text-to-speech service speaks. HA manages these providers and the pipeline. |
| Direct OpenAI Realtime | Tessera sends panel audio to OpenAI through the add-on and receives audio back. There is no separate speech-to-text or text-to-speech stage. Tessera manages the conversation session, panel context and tool bridge. |

The [standard HA pipeline](https://developers.home-assistant.io/docs/voice/pipelines/)
can use [OpenAI as its conversation agent](https://www.home-assistant.io/integrations/openai_conversation/).
That still differs from sending audio directly to OpenAI Realtime. HA also
supports conversation continuity through its
[conversation API](https://developers.home-assistant.io/docs/intent_conversation_api/),
when supported by the selected agent. Follow-up questions are therefore not
exclusive to the direct audio route. Speed and cost depend on the complete setup
and need separate measurements.

The experiment here is a hybrid: **direct OpenAI audio with HA Assist tools for
light and switch commands**. OpenAI still interprets the request. The add-on resolves the
tile label and calls HA's tool to execute it; it does not invoke a second HA
conversation agent. The existing direct-service route also operates devices
through HA. Switching the light-control setting changes only this execution
step, not the speech pipeline.

Consequently, the token measurements below compare two command execution routes
under the same OpenAI conversation. They do not compare OpenAI Realtime with a
full HA Assist speech pipeline. The latter is a separate possible integration,
not implemented by this experiment. Claude currently uses HA speech services
around Tessera's own Claude conversation layer, rather than delegating the full
conversation to HA's agent.

The physical panel currently prepares a bounded whole reply before playback.
Native Realtime audio and experimental full duplex do not yet mean fully streamed
playback from the first generated audio chunk.

## Set up and compare

1. In Home Assistant, add **Model Context Protocol Server** under Settings →
   Devices & services, with Assist enabled. This experiment needs the specific
   `/api/mcp/assist` endpoint, available in the tested HA 2026.9.3 installation.
   An older server without this endpoint is refused; the app does not silently
   switch to another API. Follow the [official setup instructions](https://www.home-assistant.io/integrations/mcp_server/).
2. Expose a test light or switch to Assist. Put it on the panel and give its tile
   a label. Use a dimmable light to test brightness.
3. Stop active voice sessions, including a physical panel's warm voice session
   if wake-word listening is enabled. In Tessera **Settings → Voice assistant →
   Assist control experiment**, choose **Home Assistant Assist**. Saving checks
   the installed tools before enabling this route. No extra provider key or
   publicly reachable HA server is needed; the add-on uses its existing HA connection.
4. Start voice and ask to turn that light or switch on or off using its tile label.
   For a dimmable light, try a percentage such as forty percent, then zero to turn
   it off. Relative changes first read the current brightness through the existing
   target tool; they do not infer the current level.
   Check the actual state in HA. Repeat with the existing route to compare.
   The same choice applies to OpenAI and Claude, in the browser and on the panel.

Light/switch on/off and dimmable light brightness are part of this experiment.
Music, current information and other commands retain their existing routes. Audio drivers,
firmware size, wake words and screen layouts are unchanged.

The `HassLightSet` tool is optional when enabling Assist, so on/off still works
on HA setups without that tool. A brightness command requires its compatible
schema and a light that HA reports as dimmable. HA's intent accepts whole
percentages: fractional requests are rounded to the nearest percent, with any
positive request kept at least one percent. Only an explicit zero turns it off.
A missing or incompatible brightness tool returns an error, without switching
to the direct-service route.

## Boundaries

The shared dispatcher refreshes exposure and active-page context before resolving
the spoken name. Visible tile labels retain priority over HA names and aliases.
The adapter passes the resolved entity id as the Assist tool's name, restricted
to that entity's light or switch domain. It refuses a conflicting exposed alias
in the same domain before invoking HA and checks the device's available actions.
HA rechecks exposure and handles the intent itself. Tile labels are never saved
as global HA aliases.

Tool names and their targeting schema are discovered from the server, with a
short cache for the schema only. Permissions are not cached. Failed requests,
timeouts and invalid receipts do not fall back or retry a potentially executed
command. Duplicate provider call ids retain the existing receipt deduplication.
Only a receipt for the exact requested entity allows silent completion of a simple command.
Acceptance is not proof that the physical lamp changed state.

The local adapter is limited to HA's stateless JSON MCP HTTP endpoint. It is not
a general MCP client and does not support arbitrary servers or tools. Credentials
stay in the add-on. The intent matcher and response format follow the installed
HA source, particularly `helpers/intent.py`, `helpers/llm.py` and
`components/mcp_server/`.

## What the measurements mean

`Voice on/off command` and `Voice brightness command` logs report the selected route and milliseconds from the
shared dispatcher through context refresh and the action receipt. They exclude
recognition, reply playback and the eventual physical state change. Unconfirmed
commands are marked separately. Names, entity ids and utterances are not logged.

The OpenAI WebSocket relay used by physical panels also logs provider-reported
input/output tokens, cached input and text/audio input for each response. Missing
usage is unknown, never zero. Browser WebRTC usage is not measured by this relay.
Compare the same utterance and context, and distinguish cold sessions from cached
input. One sample is not a performance guarantee.

The experiment deliberately keeps the model's prompt and tool schema unchanged:
only tool execution changes. It therefore offers no inherent reduction of input
tokens. Reusing Assist first tests behavior and maintenance cost; reducing the
model context is a separate measurement and design decision.
