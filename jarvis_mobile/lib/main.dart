import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/io.dart';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';
import 'package:permission_handler/permission_handler.dart';
import 'dart:ui';
import 'dart:async';

class MyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback = (X509Certificate cert, String host, int port) => true;
  }
}

void main() {
  HttpOverrides.global = MyHttpOverrides();
  runApp(const INDRAApp());
}

class INDRAApp extends StatelessWidget {
  const INDRAApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'INDRA',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF030508),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00E5FF),
          secondary: Color(0xFFB000FF),
        ),
      ),
      home: const SplashScreen(),
    );
  }
}

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  late Animation<double> _scaleAnim;
  late Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(vsync: this, duration: const Duration(seconds: 2));
    _scaleAnim = Tween<double>(begin: 0.8, end: 1.1).animate(CurvedAnimation(parent: _animController, curve: Curves.easeInOutBack));
    _fadeAnim = Tween<double>(begin: 0.0, end: 1.0).animate(CurvedAnimation(parent: _animController, curve: Curves.easeIn));
    
    _animController.forward();
    _checkSavedLogin();
  }

  Future<void> _checkSavedLogin() async {
    await Future.delayed(const Duration(seconds: 3));
    final prefs = await SharedPreferences.getInstance();
    final baseUrl = prefs.getString('INDRA_url') ?? '';
    final token = prefs.getString('INDRA_token') ?? '';
    final pairingId = prefs.getString('INDRA_pairing_id') ?? '';

    if (baseUrl.isNotEmpty && token.isNotEmpty && pairingId.isNotEmpty) {
      if (mounted) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => DashboardScreen(baseUrl: baseUrl, token: token, pairingId: pairingId),
        ));
      }
    } else {
      if (mounted) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => const LoginScreen(),
        ));
      }
    }
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF030508),
      body: Center(
        child: FadeTransition(
          opacity: _fadeAnim,
          child: ScaleTransition(
            scale: _scaleAnim,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 150,
                  height: 150,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(color: const Color(0xFF00E5FF).withOpacity(0.5), blurRadius: 40, spreadRadius: 10),
                      BoxShadow(color: const Color(0xFFB000FF).withOpacity(0.3), blurRadius: 60, spreadRadius: 20),
                    ],
                    gradient: const RadialGradient(
                      colors: [Color(0xFFE0FFFF), Color(0xFF00E5FF), Color(0xFF0055FF)],
                    ),
                  ),
                  child: const Center(
                    child: Icon(Icons.blur_on, size: 80, color: Colors.white),
                  ),
                ),
                const SizedBox(height: 40),
                const Text("I.N.D.R.A.", style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, letterSpacing: 8, color: Colors.white)),
                const SizedBox(height: 10),
                const Text("INITIALIZING PROTOCOLS...", style: TextStyle(fontSize: 12, letterSpacing: 3, color: Color(0xFF00E5FF))),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final TextEditingController _urlController = TextEditingController();
  bool _isLoading = false;
  String _error = "";

  Future<void> _connect() async {
    String inputUrl = _urlController.text.trim();
    if (inputUrl.isEmpty) return;

    setState(() { _isLoading = true; _error = ""; });

    if (!inputUrl.startsWith("http")) inputUrl = "http://$inputUrl";

    try {
      Uri uri = Uri.parse(inputUrl);
      String baseUrl = "${uri.scheme}://${uri.host}";
      if (uri.hasPort) baseUrl += ":${uri.port}";
      String token = "";
      String pairingId = "";

      if (uri.path.contains("auto-login") && uri.queryParameters.containsKey("key")) {
        final response = await http.get(uri, headers: {"Accept": "application/json", "ngrok-skip-browser-warning": "true"});
        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          token = data["token"] ?? "";
          pairingId = data["pairing_id"] ?? "";
        } else {
          throw Exception("Invalid key or server error.");
        }
      } else {
        throw Exception("Please paste the full /auto-login?key=... URL.");
      }

      if (token.isNotEmpty) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('INDRA_url', baseUrl);
        await prefs.setString('INDRA_token', token);
        await prefs.setString('INDRA_pairing_id', pairingId);

        if (mounted) {
          Navigator.of(context).pushReplacement(MaterialPageRoute(
            builder: (_) => DashboardScreen(baseUrl: baseUrl, token: token, pairingId: pairingId),
          ));
        }
      }
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF030508),
      body: Stack(
        children: [
          Positioned(top: -50, left: -50, child: Container(width: 200, height: 200, decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFFB000FF).withOpacity(0.2)), child: BackdropFilter(filter: ImageFilter.blur(sigmaX: 50, sigmaY: 50), child: Container()))),
          Positioned(bottom: -50, right: -50, child: Container(width: 250, height: 250, decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFF00E5FF).withOpacity(0.2)), child: BackdropFilter(filter: ImageFilter.blur(sigmaX: 50, sigmaY: 50), child: Container()))),
          
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24.0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                  child: Container(
                    padding: const EdgeInsets.all(32),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: Colors.white.withOpacity(0.1)),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.radar, size: 60, color: Color(0xFF00E5FF)),
                        const SizedBox(height: 20),
                        const Text("INDRA SECURE LINK", style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 2, color: Colors.white)),
                        const SizedBox(height: 30),
                        TextField(
                          controller: _urlController,
                          style: const TextStyle(color: Colors.white),
                          decoration: InputDecoration(
                            labelText: "Access URL",
                            labelStyle: const TextStyle(color: Colors.grey),
                            filled: true,
                            fillColor: Colors.black.withOpacity(0.3),
                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                            prefixIcon: const Icon(Icons.link, color: Color(0xFF00E5FF)),
                          ),
                        ),
                        const SizedBox(height: 20),
                        if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(bottom: 20), child: Text(_error, style: const TextStyle(color: Colors.redAccent, fontSize: 12), textAlign: TextAlign.center)),
                        SizedBox(
                          width: double.infinity,
                          height: 50,
                          child: ElevatedButton(
                            onPressed: _isLoading ? null : _connect,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFF00E5FF),
                              foregroundColor: Colors.black,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                            ),
                            child: _isLoading ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.black, strokeWidth: 2)) : const Text("CONNECT", style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 2)),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  final String baseUrl;
  final String token;
  final String pairingId;

  const DashboardScreen({super.key, required this.baseUrl, required this.token, required this.pairingId});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> with TickerProviderStateMixin {
  WebSocketChannel? _channel;
  IOWebSocketChannel? _audioChannel;
  final List<Map<String, String>> _messages = [];
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  
  String _status = "Connecting...";
  bool _isConnected = false;
  String _currentBaseUrl = "";
  
  bool _isRecording = false;
  final AudioRecorder _audioRecorder = AudioRecorder();
  StreamSubscription<List<int>>? _audioStreamSub;

  late AnimationController _pulseController;
  late Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _currentBaseUrl = widget.baseUrl;
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.4, end: 1.0).animate(CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut));
    _connectWebSocket();
  }

  Future<void> _autoRecoverConnection() async {
    if (widget.pairingId.isEmpty) return;
    setState(() => _status = "Magic Link Healing...");
    try {
      final response = await http.get(Uri.parse("https://ntfy.sh/INDRA_link_${widget.pairingId}/json?poll=1"));
      if (response.statusCode == 200) {
        final lines = response.body.split("\n").where((l) => l.trim().isNotEmpty).toList();
        if (lines.isNotEmpty) {
          final data = jsonDecode(lines.last);
          final newUrl = data['message'] as String;
          if (newUrl.startsWith("http")) {
            final prefs = await SharedPreferences.getInstance();
            await prefs.setString('INDRA_url', newUrl);
            setState(() => _currentBaseUrl = newUrl);
            _connectWebSocket();
            return;
          }
        }
      }
    } catch (e) {}
    setState(() => _status = "Connection Failed");
  }

  void _connectWebSocket() {
    try {
      final wsUrl = "${_currentBaseUrl.replaceFirst('http', 'ws')}/ws?token=${widget.token}";
      _channel = IOWebSocketChannel.connect(Uri.parse(wsUrl), headers: {"ngrok-skip-browser-warning": "true"});
      
      setState(() { _status = "Connected"; _isConnected = true; });

      _channel!.stream.listen((message) {
        final data = jsonDecode(message);
        if (data['type'] == 'log') {
          setState(() => _messages.add({"speaker": data['speaker'], "text": data['text']}));
          _scrollToBottom();
        } else if (data['type'] == 'sys') {
           setState(() => _messages.add({"speaker": "sys", "text": data['text']}));
           _scrollToBottom();
        } else if (data['type'] == 'status') {
          setState(() => _status = data['state'] == 'active' ? "Active" : "Sleeping");
        }
      }, onDone: () {
        if (_isConnected) setState(() => _status = "Disconnected");
        _isConnected = false;
        _autoRecoverConnection();
      }, onError: (err) {
        if (_isConnected) setState(() => _status = "Error");
        _isConnected = false;
      });
    } catch (e) {
      _autoRecoverConnection();
    }
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(_scrollController.position.maxScrollExtent, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _sendCommand() async {
    final text = _textController.text.trim();
    if (text.isEmpty) return;

    setState(() { _messages.add({"speaker": "user", "text": text}); _textController.clear(); });
    _scrollToBottom();

    try {
      await http.post(
        Uri.parse("$_currentBaseUrl/api/command"),
        headers: {"Content-Type": "application/json", "Authorization": "Bearer ${widget.token}", "ngrok-skip-browser-warning": "true"},
        body: jsonEncode({"text": text}),
      );
    } catch (e) {
      setState(() => _messages.add({"speaker": "sys", "text": "Failed to send command."}));
    }
  }

  Future<void> _startRecording() async {
    if (!await Permission.microphone.request().isGranted) return;
    setState(() => _isRecording = true);

    try {
      final audioWsUrl = "${_currentBaseUrl.replaceFirst('http', 'ws')}/ws/phone-audio?token=${widget.token}";
      _audioChannel = IOWebSocketChannel.connect(Uri.parse(audioWsUrl), headers: {"ngrok-skip-browser-warning": "true"});
      
      final stream = await _audioRecorder.startStream(const RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1));
      
      _audioStreamSub = stream.listen((data) {
        if (_audioChannel != null) {
          _audioChannel!.sink.add(data);
        }
      });
    } catch (e) {
      setState(() { _isRecording = false; _messages.add({"speaker": "sys", "text": "Failed to start microphone: $e"}); });
    }
  }

  Future<void> _stopRecording() async {
    setState(() => _isRecording = false);
    await _audioStreamSub?.cancel();
    await _audioRecorder.stop();
    _audioChannel?.sink.close();
    _audioChannel = null;
  }

  Future<void> _disconnect() async {
    _channel?.sink.close();
    _audioChannel?.sink.close();
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
    if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  @override
  void dispose() {
    _channel?.sink.close();
    _audioChannel?.sink.close();
    _audioRecorder.dispose();
    _audioStreamSub?.cancel();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF030508),
      appBar: AppBar(
        title: Row(
          children: [
            FadeTransition(
              opacity: _pulseAnim,
              child: Container(width: 8, height: 8, decoration: BoxDecoration(color: _isConnected ? const Color(0xFF00E5FF) : Colors.redAccent, shape: BoxShape.circle, boxShadow: [BoxShadow(color: (_isConnected ? const Color(0xFF00E5FF) : Colors.redAccent).withOpacity(0.5), blurRadius: 10)])),
            ),
            const SizedBox(width: 12),
            Text("INDRA", style: const TextStyle(fontWeight: FontWeight.bold, letterSpacing: 3, fontSize: 18)),
          ],
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          Center(child: Padding(padding: const EdgeInsets.only(right: 16.0), child: Text(_status, style: const TextStyle(fontSize: 10, color: Colors.grey, letterSpacing: 1)))),
          IconButton(icon: const Icon(Icons.power_settings_new, color: Colors.grey, size: 20), onPressed: _disconnect)
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isUser = msg['speaker'] == 'user';
                final isSys = msg['speaker'] == 'sys';

                if (isSys) {
                  return Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Center(child: Container(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4), decoration: BoxDecoration(color: Colors.white.withOpacity(0.05), borderRadius: BorderRadius.circular(12)), child: Text(msg['text']!, style: const TextStyle(color: Colors.grey, fontSize: 10, letterSpacing: 1)))));
                }

                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                    constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
                    decoration: BoxDecoration(
                      gradient: isUser ? const LinearGradient(colors: [Color(0xFF0F172A), Color(0xFF1E293B)]) : const LinearGradient(colors: [Color(0xFF00E5FF), Color(0xFF0088FF)]),
                      borderRadius: BorderRadius.circular(20).copyWith(bottomRight: isUser ? const Radius.circular(4) : const Radius.circular(20), bottomLeft: !isUser ? const Radius.circular(4) : const Radius.circular(20)),
                      boxShadow: [BoxShadow(color: isUser ? Colors.black26 : const Color(0xFF00E5FF).withOpacity(0.2), blurRadius: 10, offset: const Offset(0, 4))],
                    ),
                    child: Column(
                      crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                      children: [
                        Text(isUser ? "YOU" : "INDRA", style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: isUser ? Colors.grey : Colors.white.withOpacity(0.8), letterSpacing: 2)),
                        const SizedBox(height: 6),
                        Text(msg['text']!, style: TextStyle(color: isUser ? Colors.white : Colors.black87, fontSize: 14, height: 1.4, fontWeight: isUser ? FontWeight.normal : FontWeight.w500)),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Colors.white.withOpacity(0.02), border: Border(top: BorderSide(color: Colors.white.withOpacity(0.05)))),
            child: SafeArea(
              child: Row(
                children: [
                  GestureDetector(
                    onTapDown: (_) => _startRecording(),
                    onTapUp: (_) => _stopRecording(),
                    onTapCancel: () => _stopRecording(),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      width: 50, height: 50,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: _isRecording ? Colors.redAccent : Colors.white.withOpacity(0.1),
                        boxShadow: _isRecording ? [BoxShadow(color: Colors.redAccent.withOpacity(0.5), blurRadius: 20, spreadRadius: 5)] : [],
                      ),
                      child: Icon(Icons.mic, color: _isRecording ? Colors.white : const Color(0xFF00E5FF)),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: _textController,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        hintText: "Enter command...",
                        hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
                        filled: true,
                        fillColor: Colors.white.withOpacity(0.05),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                      ),
                      onSubmitted: (_) => _sendCommand(),
                    ),
                  ),
                  const SizedBox(width: 12),
                  GestureDetector(
                    onTap: _sendCommand,
                    child: Container(
                      width: 50, height: 50,
                      decoration: const BoxDecoration(shape: BoxShape.circle, gradient: LinearGradient(colors: [Color(0xFF00E5FF), Color(0xFF0088FF)])),
                      child: const Icon(Icons.send, color: Colors.black),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
