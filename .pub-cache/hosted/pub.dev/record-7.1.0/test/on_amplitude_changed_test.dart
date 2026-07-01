import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

import 'helpers/fake_record_platform.dart';
import 'helpers/test_utils.dart';

void main() {
  late FakeRecordPlatform fake;
  late AudioRecorder recorder;

  setUp(() async {
    fake = FakeRecordPlatform();
    RecordPlatform.instance = fake;
    recorder = AudioRecorder();
    await pump();
  });

  tearDown(() async {
    try {
      await recorder.dispose();
    } catch (_) {}
  });

  group('onAmplitudeChanged', () {
    test('returns a stream', () {
      expect(
        recorder.onAmplitudeChanged(const Duration(milliseconds: 300)),
        isA<Stream<Amplitude>>(),
      );
    });

    test('does not restart monitoring when called again with the same interval', () async {
      fake.isRecordingResult = true;
      const interval = Duration(milliseconds: 50);

      final values = <Amplitude>[];
      final sub1 = recorder.onAmplitudeChanged(interval).listen((_) {});
      // Second call with same interval — both backed by the same controller.
      final sub2 = recorder.onAmplitudeChanged(interval).listen(values.add);
      addTearDown(sub1.cancel);
      addTearDown(sub2.cancel);

      await Future.delayed(const Duration(milliseconds: 200));

      expect(values, isNotEmpty);
    });

    test('emits amplitude values while recording', () async {
      fake.isRecordingResult = true;

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 200));

      expect(values, isNotEmpty);
      expect(fake.calls, contains('getAmplitude'));
    });

    test('does not emit when not recording', () async {
      fake.isRecordingResult = false;

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 200));

      expect(values, isEmpty);
    });

    test('emitted amplitude matches platform result', () async {
      fake.isRecordingResult = true;
      fake.amplitudeResult = Amplitude(current: -15.0, max: -3.0);

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 150));

      expect(values.first.current, -15.0);
      expect(values.first.max, -3.0);
    });

    test('stops emitting after pause state', () async {
      fake.isRecordingResult = true;

      recorder.onStateChanged().listen((_) {});
      await pump();

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 120));
      final countAtPause = values.length;
      expect(countAtPause, greaterThan(0));

      fake.emitState(RecordState.pause);
      await pump();
      fake.isRecordingResult = false;

      await Future.delayed(const Duration(milliseconds: 120));

      expect(values.length, countAtPause);
    });

    test('stops emitting after stop state', () async {
      fake.isRecordingResult = true;

      recorder.onStateChanged().listen((_) {});
      await pump();

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 120));
      final countAtStop = values.length;
      expect(countAtStop, greaterThan(0));

      fake.emitState(RecordState.stop);
      await pump();
      fake.isRecordingResult = false;

      await Future.delayed(const Duration(milliseconds: 120));

      expect(values.length, countAtStop);
    });

    test('continues monitoring after interval change', () async {
      fake.isRecordingResult = true;

      final values = <Amplitude>[];
      final sub = recorder
          .onAmplitudeChanged(const Duration(milliseconds: 50))
          .listen(values.add);
      addTearDown(sub.cancel);

      await Future.delayed(const Duration(milliseconds: 150));
      final countBefore = values.length;
      expect(countBefore, greaterThan(0));

      // Change interval — timer restarts; monitoring must continue.
      recorder.onAmplitudeChanged(const Duration(milliseconds: 60));

      await Future.delayed(const Duration(milliseconds: 200));
      expect(values.length, greaterThan(countBefore));
    });
  });
}
