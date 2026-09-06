"use strict";
/**
 * 골프존 Auto.js 서비스
 * 역할: Python(Termux)의 명령을 받아 UI 탭/스와이프 실행 + 화면 덤프
 *
 * 사전 준비:
 *   1. AutoJs6 설치 → 설정 → 접근성 → AutoJs6 활성화
 *   2. 이 파일을 Auto.js에서 열고 실행 (상시 실행 유지)
 *   3. Termux에서 python3 golfzon_auto.py 실행
 *
 * 통신 파일:
 *   /sdcard/golfzon/ready.json  시작 신호 (Auto.js → Python)
 *   /sdcard/golfzon/cmd.json    명령      (Python → Auto.js)
 *   /sdcard/golfzon/done.json   완료 신호 (Auto.js → Python)
 *   /sdcard/golfzon/dump.json   화면 덤프 (Auto.js → Python)
 */

const BASE      = "/sdcard/golfzon/";
const CMD_FILE  = BASE + "cmd.json";
const DONE_FILE = BASE + "done.json";
const DUMP_FILE = BASE + "dump.json";
const READY_FILE = BASE + "ready.json";
const VERSION   = "1.0";

// ── 초기화 ────────────────────────────────────────────
files.ensureDir(BASE);

if (!auto.waitFor()) {
    toast("설정 → 접근성 → AutoJs6 → 활성화 후 재실행");
    exit();
}

// 시작 신호 기록
files.write(READY_FILE, JSON.stringify({
    version: VERSION,
    screen_w: device.width,
    screen_h: device.height,
    time: new Date().toISOString()
}));

toast("골프존 Auto.js 서비스 시작 (v" + VERSION + ")");
log("=== 골프존 Auto.js 서비스 v" + VERSION + " ===");
log("화면: " + device.width + "x" + device.height);
log("명령 대기: " + CMD_FILE);

// ── 화면 덤프 (Accessibility API) ─────────────────────
function dumpScreen() {
    var nodes = [];
    var seen  = {};

    var classes = [
        "android.widget.TextView",
        "android.widget.Button",
        "android.widget.ImageButton",
        "android.widget.ImageView",
        "android.view.View",
        "android.widget.LinearLayout",
        "android.widget.FrameLayout",
        "android.widget.RelativeLayout",
        "android.widget.ScrollView",
    ];

    classes.forEach(function(cls) {
        try {
            className(cls).find().forEach(function(node) {
                var b   = node.bounds();
                var key = b.left + "," + b.top + "," + b.right + "," + b.bottom;
                if (seen[key]) return;

                var txt  = node.text()  || "";
                var desc = node.desc()  || "";
                var id   = node.id()    || "";
                var click = node.clickable();

                if (txt || desc || click) {
                    seen[key] = true;
                    nodes.push({
                        text:      txt,
                        desc:      desc,
                        id:        id,
                        bounds:    [b.left, b.top, b.right, b.bottom],
                        clickable: click
                    });
                }
            });
        } catch(e) { /* 일부 클래스 접근 실패 무시 */ }
    });

    files.write(DUMP_FILE, JSON.stringify(nodes));
    return nodes.length;
}

// ── 결과 기록 ─────────────────────────────────────────
function writeResult(status, extra) {
    var result = { status: status };
    if (extra) {
        Object.keys(extra).forEach(function(k) { result[k] = extra[k]; });
    }
    files.write(DONE_FILE, JSON.stringify(result));
}

// ── 명령 실행 ─────────────────────────────────────────
function execAction(cmd) {
    var w = device.width, h = device.height;

    switch (cmd.action) {

        case "launch":
            app.launchPackage(cmd.pkg || "com.golfzon.android");
            sleep(cmd.wait || 4000);
            writeResult("ok");
            break;

        case "tap_text": {
            var el = text(cmd.text).findOne(cmd.timeout || 3000);
            if (el) {
                el.click();
                sleep(cmd.wait || 1200);
                writeResult("ok", { found: true });
            } else {
                writeResult("ok", { found: false });
            }
            break;
        }

        case "tap_contains": {
            var el = textContains(cmd.text).findOne(cmd.timeout || 3000);
            if (el) {
                el.click();
                sleep(cmd.wait || 1200);
                writeResult("ok", { found: true });
            } else {
                writeResult("ok", { found: false });
            }
            break;
        }

        case "tap_desc": {
            var el = desc(cmd.text).findOne(cmd.timeout || 2000);
            if (!el) el = descContains(cmd.text).findOne(1000);
            if (el) {
                el.click();
                sleep(cmd.wait || 1200);
                writeResult("ok", { found: true });
            } else {
                writeResult("ok", { found: false });
            }
            break;
        }

        case "tap_xy":
            gesture(200, [[cmd.x, cmd.y]]);
            sleep(cmd.wait || 1200);
            writeResult("ok");
            break;

        case "dump": {
            var count = dumpScreen();
            writeResult("ok", { count: count });
            break;
        }

        case "swipe_up":
            swipe(w / 2, Math.round(h * 0.70), w / 2, Math.round(h * 0.30), 600);
            sleep(cmd.wait || 800);
            writeResult("ok");
            break;

        case "swipe_down":
            swipe(w / 2, Math.round(h * 0.30), w / 2, Math.round(h * 0.70), 600);
            sleep(cmd.wait || 800);
            writeResult("ok");
            break;

        case "back":
            back();
            sleep(cmd.wait || 1200);
            writeResult("ok");
            break;

        case "sleep":
            sleep(cmd.ms || 1000);
            writeResult("ok");
            break;

        case "screen_size":
            writeResult("ok", { width: device.width, height: device.height });
            break;

        case "quit":
            writeResult("ok");
            files.remove(READY_FILE);
            toast("Auto.js 서비스 종료");
            exit();
            break;

        default:
            writeResult("error", { message: "unknown action: " + cmd.action });
    }
}

// ── 메인 루프 ─────────────────────────────────────────
var lastSeq = -1;

while (true) {
    sleep(300);

    if (!files.exists(CMD_FILE)) continue;

    var cmdStr;
    try {
        cmdStr = files.read(CMD_FILE);
        if (!cmdStr || !cmdStr.trim()) continue;
    } catch(e) { continue; }

    var cmd;
    try {
        cmd = JSON.parse(cmdStr);
    } catch(e) { continue; }

    var seq = (typeof cmd.seq !== "undefined") ? cmd.seq : 0;
    if (seq <= lastSeq) continue;
    lastSeq = seq;

    if (files.exists(DONE_FILE)) files.remove(DONE_FILE);

    log("[seq " + seq + "] " + cmd.action
        + (cmd.text ? " '" + cmd.text + "'" : "")
        + (cmd.x    ? " (" + cmd.x + "," + cmd.y + ")" : ""));

    try {
        execAction(cmd);
    } catch(e) {
        log("오류: " + e.message);
        try { writeResult("error", { message: e.message }); } catch(e2) {}
    }
}
