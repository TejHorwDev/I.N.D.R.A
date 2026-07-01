import 'package:flutter/material.dart';

import 'package:record_example/audio_player.dart';
import 'package:record_example/audio_recorder.dart';

void main() => runApp(const MyApp());

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  String? audioPath;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Center(
          child: Stack(
            children: [
              Offstage(
                offstage: audioPath != null,
                child: Recorder(
                  onStop: (path) {
                    debugPrint('Recorded file path: $path');
                    setState(() => audioPath = path);
                  },
                ),
              ),
              if (audioPath != null)
                AudioPlayer(
                  source: audioPath!,
                  onDelete: () => setState(() => audioPath = null),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
