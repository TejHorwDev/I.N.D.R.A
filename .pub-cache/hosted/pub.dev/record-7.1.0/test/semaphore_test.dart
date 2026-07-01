import 'package:flutter_test/flutter_test.dart';
import 'package:record/src/util/semaphore.dart';

import 'helpers/test_utils.dart';

void main() {
  group('Semaphore', () {
    test('acquire completes immediately when not held', () async {
      final sem = Semaphore();
      await expectLater(sem.acquire(), completes);
    });

    test('release after acquire succeeds', () async {
      final sem = Semaphore();
      await sem.acquire();
      expect(() => sem.release(), returnsNormally);
    });

    test('release without acquire throws StateError', () {
      final sem = Semaphore();
      expect(() => sem.release(), throwsStateError);
    });

    test('double release throws StateError', () async {
      final sem = Semaphore();
      await sem.acquire();
      sem.release();
      expect(() => sem.release(), throwsStateError);
    });

    test('second acquire blocks while permit is held', () async {
      final sem = Semaphore();
      await sem.acquire();

      var secondCompleted = false;
      sem.acquire().then((_) => secondCompleted = true);

      await pump();
      expect(secondCompleted, isFalse);

      sem.release();
      await pump();
      expect(secondCompleted, isTrue);
    });

    test('queued acquires are granted in FIFO order', () async {
      final sem = Semaphore();
      await sem.acquire();

      final order = <int>[];
      sem.acquire().then((_) => order.add(1));
      sem.acquire().then((_) => order.add(2));
      sem.acquire().then((_) => order.add(3));

      await pump();
      expect(order, isEmpty);

      sem.release();
      await pump();
      sem.release();
      await pump();
      sem.release();
      await pump();

      expect(order, equals([1, 2, 3]));
    });

    test('can reacquire after release', () async {
      final sem = Semaphore();
      await sem.acquire();
      sem.release();
      await expectLater(sem.acquire(), completes);
    });

    test('maxCount is 1', () {
      expect(Semaphore().maxCount, equals(1));
    });
  });
}
