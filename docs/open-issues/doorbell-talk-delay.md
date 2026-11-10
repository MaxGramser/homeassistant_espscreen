# A doorbell's Talk reaches a Reolink about 3 seconds late

The screen's voice is heard clearly at a Reolink, about 3 seconds late, and Home Assistant's own talk button is as late.

Measured 2026-11-10 on Home Assistant 2026.11 with go2rtc 1.9.14: a beep sent through the bridge was heard by the camera's own microphone
2.6 seconds later. The screen holds a voice for at most 0.4 s and the app for at most 0.3 s. Home Assistant only brokers the WebRTC session,
and go2rtc writes every audio packet to the camera at once (`pkg/rtsp/consumer.go`), so what is left is the camera's RTSP backchannel.
go2rtc #939 reports the same on a Reolink PoE doorbell.

Reolink's own protocol (Baichuan, as neolink uses) is reported to be faster. It is a camera brand's route beside Home Assistant, and Home
Assistant is the reference here, so it stays out.
