"use strict";
// API hosts, tried in order; the first that answers is remembered. Add a second host here (e.g. a custom domain) if *.workers.dev is blocked.
const API_BASES = ["https://divya.n8n00101.workers.dev/api"];
let API = API_BASES[Math.min(parseInt(localStorage.getItem("dv_apiIdx") || "0", 10) || 0, API_BASES.length - 1)];
const APP_URL = "https://divya-app.n8n00101.workers.dev";
const BASE = new URL(".", location.href.split("#")[0].split("?")[0].replace(/\/setup$/, "/")).href; // works at / and at /divya-edit-worker/app/
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const store = { get: (k, d) => { try { const v = localStorage.getItem("dv_" + k); return v === null ? d : JSON.parse(v); } catch { return d; } }, set: (k, v) => localStorage.setItem("dv_" + k, JSON.stringify(v)), del: k => localStorage.removeItem("dv_" + k) };
const S = { token: store.get("token", ""), number: store.get("number", ""), acct: store.get("acct", null), lang: store.get("lang", "te"), voice: store.get("voice", true), vf: store.get("vf", false), theme: store.get("theme", "auto"), wake: store.get("wake", false), consent: store.get("consent", false) };
const isAndroid = /android/i.test(navigator.userAgent), isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const tz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata"; } catch { return "Asia/Kolkata"; } })();

/* ---------- text ---------- */
const T = {
  te: {
    skip: "Content ki vellu", numLabel: "WhatsApp number", codeLabel: "6 ankela code",
    loginSub: "Nee WhatsApp number ivvu. Code WhatsApp ki vasthundi.", loginSub2: "Nee personal AI. Login avvu leda kotha account create cheyyi.", loginWays: "Login vidhanam", tabLogin: "Login", tabSignup: "Sign up", tabWa: "WhatsApp code",
    idLabel: "Email leda phone number", idPh: "Email leda phone number", pwLabel: "Password", newPwLabel: "Password (kanisam 8)", nameLabel: "Nee peru", emailLabel: "Email", phoneLabel: "Phone (WhatsApp) — optional", showPw: "Password chupinchu",
    logIn: "Login", forgot: "Password marchipoyava?", createAcct: "Account create cheyyi", suHint: "Phone WhatsApp code tho verify ayyaka matrame link avuthundi. Kotha accounts Free plan lo untayi.",
    forgotT: "Password reset", forgotSub: "Nee email leda verified phone ivvu. Reset code nee verified WhatsApp ki vasthundi.", sendResetCode: "Reset code pampu", backLogin: "Login ki venakki", setPw: "Kotha password set cheyyi", rsSentTo: n => `${n} ki WhatsApp lo code pampa.`,
    verifyPhoneT: "Phone verify", pvSentTo: n => `${n} ki WhatsApp lo 6 ankela code pampa.`, later: "Tarvatha", needId: "Email leda phone ivvu.", needPw: "Password ivvu.", triesLeft: n => ` (${n} tries migilayi)`,
    netBlockedT: "Divya server ki connect avvaledu.", netBlocked: "Nee network (ISP) *.workers.dev ni block chestundochu. Mobile data ↔ Wi-Fi marchi chudu, leda Private DNS (1.1.1.1 / dns.google) on cheyyi.", offline: "Internet ledu. Connection chusi malli try cheyyi.", retry: "Malli try cheyyi",
    account: "Account", phoneOk: n => `Phone: ${n} ✓ verified`, phoneNone: "Phone link avvaledu. Link chesthe phone tho login + password reset vasthayi.", phonePend: n => `Phone ${n}: inka verify avvaledu.`, sendCode: "Code pampu", phoneLinked: "Phone link ayyindi ✓", delAcct: "Account delete cheyyi", delWarn: "Nee account, login, app chat history delete avuthayi. Password tho confirm cheyyi.", delConfirm: "Delete confirm", deleted: "Account delete ayyindi.", getCode: "Code pampu", verify: "Login", codeHint: "Code raakapothe WhatsApp lo Divya ki \"login\" ani pampu.", changeNum: "Number marchu", codeSentTo: n => `+${n} ki WhatsApp lo code pampa.`, waitCode: "Code already pampa. WhatsApp chudu.",
    sEdit: "Video edit", sProfile: "Profile", gEdit: "Video edit", tHome: "Home", tEdit: "Edit", tVoice: "Voice", tChat: "Chat", tSetup: "Setup", tabsLabel: "Main tabs", openProfile: "Profile open cheyyi",
    editsLeftT: "Free edits migilinavi", notVerified: "verify kaaledu", quotaSub: (u, l) => `Ee nela ${u}/${l} vaadavu · 1st ki reset`, unlimited: "Unlimited", unlimitedSub: "Owner/friend — limit ledu",
    editIntro: "Nee video upload cheyyi leda link ivvu. Nuvvu select chesina type ki taggattu Divya edit chesi isthundi.", yourVideo: "Nee video", srcUpload: "Upload", srcLink: "Link", pickVideo: "Video select cheyyi (24 MB varaku)", linkLabel: "Video link", linkPh: "Google Drive / YouTube / direct video link",
    uploadHelp: "24 MB varaku direct upload. Pedda videos ki Link vaadu.", linkHelp: "Drive file ni 'Anyone with the link' ga share cheyyi. YouTube/Instagram links konni sarlu maa server nunchi download avvavu — appudu Drive link ivvu.",
    videoType: "Video type", kLong: "Long video / Documentary", kLongSub: "Faceless · story flow, captions, music", kShort: "Faceless short", kShortSub: "9:16 · hook, fast cuts, pedda captions", kFace: "Face video", kFaceSub: "Talking head · pauses cut, zooms, captions",
    editLang: "Captions bhasha", lenAuto: "Auto", lenFull: "Full length", notesLabel: "Extra cheppalsindi (optional)", notesPh: "ex: modati 10 seconds teesey, music thakkuva",
    editBtn: "Edit start cheyyi", dlEdit: "Edit chesina video download", needKind: "Video type select cheyyi.", needSrc: "Video select cheyyi leda link ivvu.", tooBig: "Ee file 24 MB kante pedda. Link vaadu.", uploading: p => `Upload ${p}%`,
    editsLine: (left, l) => l === null ? "Unlimited edits (owner/friend)" : `Ee nela ${left}/${l} free edits migilayi`,
    jobQueued: "Edit queue lo undi", jobRunSub2: "Konchem time paduthundi. Ready ayyaka ikkade download vasthundi.", jobDoneSub2: "Download cheyyi (3 rojulu untundi).", jobFailSub2: "Ee edit nee free count lo lekka ledu. Link/file chusi malli try cheyyi.",
    email: "Email", phone: "Phone", planL: "Plan", planFree: "Free", planPrem: "Premium (owner/friend)", waLogin: "WhatsApp login", f0: "Nelaki 10 video edits",
    openMenu: "Menu open cheyyi", closeMenu: "Menu close cheyyi", menu: "Main menu", heyDivya: "Hey Divya — matladu", quickActions: "Shortcuts",
    sHome: "Home", sChat: "Chat", sVoice: "Voice assistant", sConnect: "Accounts connect", sSetup: "Server & API setup", sPlan: "Subscription", sDownload: "App download", sSettings: "Settings", logout: "Logout",
    gChat: "Chat", gVoice: "Voice", gConnect: "Connect", gSetup: "Server setup", gPlan: "Plan", gDownload: "Download", gSettings: "Settings",
    screen: n => `${n} screen`,
    hello: h => h < 12 ? "నమస్కారం, good morning" : h < 17 ? "నమస్కారం, good afternoon" : "నమస్కారం, good evening", greetSub: "Ee roju em cheddam?", heySub: "Tap chesi matladu: call, WhatsApp, open, songs, reminders",
    noJob: "Edit emi ledu", noJobSub: "Edit tab lo nee video ivvu.",
    online: "Online", thinking: "Typing…", listening: "Vintunna…", releaseToSend: "Vadilithe pamputha", typeMsg: "Message…", holdMic: "Mic ni press chesi pattuko, matladu, vadilai.", holdToTalk: "Press chesi pattukoni matladu, leda message pampu", attachImage: "Image pampu",
    emptyTitle: "Hi, nenu Divya", emptySub: "Chat cheyyi, matladu, leda pani cheppu.", s1: "YouTube open cheyyi", s2: "Ippudu time entha?", s3: "Nuvvu em cheyagalavu?",
    length: "Length",
    jobRun: "Edit jarugutondi", jobRunSub: "Konchem time paduthundi. Ready ayyaka WhatsApp lo pampistha.", jobDone: "Edit ready ✓", jobDoneSub: "WhatsApp chudu.", jobFail: "Edit fail ayyindi", jobFailSub: "Malli try cheyyi.", started: "Edit start chesa!",
    tapToTalk: "Tap chesi matladu", vIdle: "Tap chesi matladu", vWake: "\"Hey Divya\" kosam vintunna…", vListen: "Vintunna… cheppu", vThink: "Alochistunna…", vSpeak: "Cheptunna…", vNoSR: "Ee browser lo always-listening ledu. Orb ni press chesi pattukoni matladu.",
    wakeSub: "App screen meeda open unnantha sepu vintundi", freeTitle: "Free:", freeList: "video edits (nelaki 10), calls, WhatsApp message, apps/sites open, songs, reminders, time, weather, chinna questions.", proTitle: "Pro:", proList: "unlimited edits, multi-step agent pani, long research, account automation.",
    voiceHonest: "Divya app open ga, screen meeda unnappude vintundi (web app background lo vinadu). Call/WhatsApp silent ga pampadu: dialer leda WhatsApp ni anni fill chesi open chestundi, nuvvu Call/Send nokkali. Voice recognition browser service (Chrome lo Google) dwara jarugutundi.",
    callBtn: n => `Call ${n}`, waBtn: "WhatsApp open cheyyi", openBtn: n => `${n} open cheyyi`, playBtn: "YouTube lo vinu", calBtn: "Google Calendar lo add cheyyi", subBtn: "Plans chudu", pickContact: "Contacts nunchi select", typeNumber: "Number type cheyyi",
    noNumber: n => `${n} number naa daggara ledu. "save ${n} 98xxxxxxxx" ani cheppu, leda contacts nunchi select cheyyi.`, askNumber: n => `${n} phone number?`, saved: (n, x) => `${n} number save chesa (+${x}). Ee phone lo matrame untundi.`,
    remFire: t => `Reminder: ${t}`, notifTitle: "Divya reminder",
    connectNote: "Login page browser lo open avuthundi. Connect ayyaka ikkadiki tirigi raa.", connect: "Connect", connectedP: "Connected", soon: "Tvaralo", 
    setupIntro: "Divya nee sontha backend ni NEE accounts lo set chestundi — nee permission tharvathe. Ippudu: nee email tho login, API keys (free) add cheyyi. Keys encrypt chesi save avthayi, nee requests ki matrame vaadutham.",
    googleRow: "Continue with Google", googleSub: "Nee email ni setup ki vaadutham", continueGoogle: "Continue",
    consent: "Naa keys ni Divya encrypt chesi save chesi, naa requests kosam matrame vaadadaniki permission istunna.", guideBtn: "🔊 Voice tho step-by-step setup",
    needConsent: "Mundu permission box tick cheyyi.", allow: "Allow", cancel: "Cancel", save: "Save", next: "Next step", done: "Ayyindi",
    stepNot: "Inka ledu", stepOk: w => `Connected${w ? " · " + w : ""}`, stepFail: "Test fail", oneTap: "One-tap connect", openCreate: "Open & key create", pasteKey: "Key ikkada paste cheyyi", paste: "Paste", testSave: "Test & save", test: "Test", remove: "Remove", oauthSoon: "OAuth login tvaralo; ippudu token paste cheyyi.",
    foundKey: (n, l) => `${n} key dorikindi (…${l}). Save cheyyana?`, keySaved: n => `${n} key save ayyindi, test pass.`, keyBad: n => `Idi ${n} key laaga ledu.`,
    guideStep: (n, d) => `${n} setup. ${d} Nenu page open chestha. Nee email tho login avvu, key create chesi copy cheyyi, tarvatha Divya ki tirigi raa.`, guideReturn: "Key copy chesava? Clipboard nunchi chustunna.", guidePaste: "Key ni box lo paste chesi Test & save nokku.", guideDone: "Anni steps ayyayi. Super!", guideNextQ: n => `Next: ${n}. Continue cheyyana?`,
    serverTitle: "Nee sontha server:", serverText: "Cloudflare token tho Divya nee account lo nee Worker deploy chestundi — tvaralo (prathi sari nee OK tho).", noPasswords: "Divya passwords save cheyyadu, accounts silent ga create cheyyadu, captchas bypass cheyyadu. Prathi provider lo login nuvve chestav.",
    d_openrouter: "Free AI models tho brain (backup).", d_groq: "Fast brain + voice-to-text.", d_gemini: "Images/screenshots chadavadaniki.", d_cloudflare: "Nee sontha server (Worker) kosam.", d_github: "Video machine (Actions) kosam.", d_huggingface: "AI models/voices kosam.",
    planNow: (p, u, l) => `Nee plan: ${p === "premium" ? "Premium (owner/friend access)" : "Free"}. Ee nela video edits: ${l === null ? `${u} (limit ledu)` : `${u}/${l}`}.`,
    freePlan: "Free", f1: "Voice commands: call, WhatsApp, open apps, songs, reminders, time, weather", f2: "Chat & chinna questions", f3: "Blind users kosam voice-first mode", f4: "Nee sontha API keys vaadochu",
    p1: "Unlimited video edits", p2: "Multi-step agent pani, long research", p3: "Account automation (post/upload — nee OK tho)", priceSoon: "Price: tvaralo", comingSoon: "Tvaralo vasthundi", noPayNote: "Ippudu payments levu. Pro ready ayyaka cheptham.",
    installNow: "App install cheyyi", installed: "Divya ee device lo already app laaga install ayyindi ✓", canInstall: "Ee browser lo one-tap install undi.", cantPrompt: "Ee browser auto install chupinchadu — kinda steps follow avvu.", notApk: "Idi browser nunchi app laaga install avuthundi (PWA). Play Store APK kaadu.",
    and1: "Chrome lo ee page open cheyyi.", and2: "Paina \"App install cheyyi\" nokku, leda menu (⋮) → \"Install app\" / \"Add to Home screen\".", and3: "Home screen lo Divya icon vasthundi.",
    ios1: "Safari lo ee page open cheyyi.", ios2: "Share (□↑) nokku → \"Add to Home Screen\".", ios3: "\"Add\" nokku. Home screen nunchi open cheyyi.",
    pc1: "Chrome/Edge address bar lo install icon (⊕ / monitor) nokku.", pc2: "Leda menu → \"Install Divya\" / \"Apps → Install this site as an app\".",
    language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "Mic lo adigithe Divya gattiga reply chestundi", voiceFirst: "Voice-first mode", voiceFirstSub: "Prathi result gattiga cheptundi, answer tarvatha malli vintundi (blind users kosam)", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts",
    netErr: "Network problem. Malli try cheyyi.", micDenied: "Mic permission ivvu (browser settings lo).", noRec: "Ee browser lo voice record avvadu.", loggedIn: n => `${n} tho login`, orDone: "OpenRouter connect ayyindi ✓", orFail: "OpenRouter connect avvaledu.",
  },
  en: {
    skip: "Skip to content", numLabel: "WhatsApp number", codeLabel: "6-digit code",
    loginSub: "Enter your WhatsApp number. The code comes on WhatsApp.", loginSub2: "Your personal AI. Log in or create an account.", loginWays: "Ways to log in", tabLogin: "Log in", tabSignup: "Sign up", tabWa: "WhatsApp code",
    idLabel: "Email or phone number", idPh: "Email or phone number", pwLabel: "Password", newPwLabel: "Password (8+ characters)", nameLabel: "Your name", emailLabel: "Email", phoneLabel: "Phone (WhatsApp) — optional", showPw: "Show password",
    logIn: "Log in", forgot: "Forgot password?", createAcct: "Create account", suHint: "Your phone links only after you verify it with a WhatsApp code. New accounts start on the Free plan.",
    forgotT: "Reset password", forgotSub: "Enter your email or verified phone. The reset code goes to your verified WhatsApp.", sendResetCode: "Send reset code", backLogin: "Back to log in", setPw: "Set new password", rsSentTo: n => `Code sent on WhatsApp to ${n}.`,
    verifyPhoneT: "Verify phone", pvSentTo: n => `We sent a 6-digit code on WhatsApp to ${n}.`, later: "Later", needId: "Enter your email or phone.", needPw: "Enter your password.", triesLeft: n => ` (${n} tries left)`,
    netBlockedT: "Can't reach Divya's server.", netBlocked: "Your network (ISP) may be blocking *.workers.dev. Switch between mobile data and Wi-Fi, or turn on Private DNS (1.1.1.1 / dns.google).", offline: "You're offline. Check your connection and try again.", retry: "Try again",
    account: "Account", phoneOk: n => `Phone: ${n} ✓ verified`, phoneNone: "No phone linked. Link one to log in by phone and reset your password.", phonePend: n => `Phone ${n}: not verified yet.`, sendCode: "Send code", phoneLinked: "Phone linked ✓", delAcct: "Delete account", delWarn: "This deletes your account, login and app chat history. Confirm with your password.", delConfirm: "Confirm delete", deleted: "Account deleted.", getCode: "Send code", verify: "Log in", codeHint: "No code? Send \"login\" to Divya on WhatsApp.", changeNum: "Change number", codeSentTo: n => `Code sent on WhatsApp to +${n}.`, waitCode: "Code already sent. Check WhatsApp.",
    sEdit: "Edit video", sProfile: "Profile", gEdit: "Edit video", tHome: "Home", tEdit: "Edit", tVoice: "Voice", tChat: "Chat", tSetup: "Setup", tabsLabel: "Main tabs", openProfile: "Open profile",
    editsLeftT: "Free edits left", notVerified: "not verified", quotaSub: (u, l) => `${u} of ${l} used this month · resets on the 1st`, unlimited: "Unlimited", unlimitedSub: "Owner/friend — no limit",
    editIntro: "Upload your video or paste its link. Divya edits it for the type you pick.", yourVideo: "Your video", srcUpload: "Upload", srcLink: "Link", pickVideo: "Choose a video (up to 24 MB)", linkLabel: "Video link", linkPh: "Google Drive / YouTube / direct video link",
    uploadHelp: "Direct upload up to 24 MB. For bigger videos use Link.", linkHelp: "Share Drive files as 'Anyone with the link'. YouTube/Instagram links sometimes can't be downloaded by our server — use a Drive link then.",
    videoType: "Video type", kLong: "Long video / Documentary", kLongSub: "Faceless · story flow, captions, music", kShort: "Faceless short", kShortSub: "9:16 · hook, fast cuts, big captions", kFace: "Face video", kFaceSub: "Talking head · cut pauses, zooms, captions",
    editLang: "Captions language", lenAuto: "Auto", lenFull: "Full length", notesLabel: "Extra notes (optional)", notesPh: "e.g. cut the first 10 seconds, keep music low",
    editBtn: "Start edit", dlEdit: "Download edited video", needKind: "Pick a video type.", needSrc: "Choose a video or paste a link.", tooBig: "This file is over 24 MB. Use a link.", uploading: p => `Uploading ${p}%`,
    editsLine: (left, l) => l === null ? "Unlimited edits (owner/friend)" : `${left} of ${l} free edits left this month`,
    jobQueued: "Edit is queued", jobRunSub2: "This takes a few minutes. The download appears here when it's ready.", jobDoneSub2: "Download it (kept for 3 days).", jobFailSub2: "This one didn't count toward your free edits. Check the link/file and try again.",
    email: "Email", phone: "Phone", planL: "Plan", planFree: "Free", planPrem: "Premium (owner/friend)", waLogin: "WhatsApp login", f0: "10 video edits a month",
    openMenu: "Open menu", closeMenu: "Close menu", menu: "Main menu", heyDivya: "Hey Divya — talk", quickActions: "Shortcuts",
    sHome: "Home", sChat: "Chat", sVoice: "Voice assistant", sConnect: "Connect accounts", sSetup: "Server & API setup", sPlan: "Subscription", sDownload: "Download app", sSettings: "Settings", logout: "Log out",
    gChat: "Chat", gVoice: "Voice", gConnect: "Connect", gSetup: "Server setup", gPlan: "Plan", gDownload: "Download", gSettings: "Settings",
    screen: n => `${n} screen`,
    hello: h => h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening", greetSub: "What shall we do today?", heySub: "Tap and speak: call, WhatsApp, open, songs, reminders",
    noJob: "No edit yet", noJobSub: "Give Divya your video in the Edit tab.",
    online: "Online", thinking: "Typing…", listening: "Listening…", releaseToSend: "Release to send", typeMsg: "Message…", holdMic: "Press and hold the mic, speak, then let go.", holdToTalk: "Press and hold to talk, or send message", attachImage: "Send image",
    emptyTitle: "Hi, I'm Divya", emptySub: "Chat, talk, or give me a task.", s1: "Open YouTube", s2: "What time is it?", s3: "What can you do?",
    length: "Length",
    jobRun: "Editing your video", jobRunSub: "This takes a few minutes.", jobDone: "Edit ready ✓", jobDoneSub: "Check WhatsApp.", jobFail: "Edit failed", jobFailSub: "Try again.", started: "Started! It'll arrive on WhatsApp.",
    tapToTalk: "Tap to talk", vIdle: "Tap to talk", vWake: "Listening for \"Hey Divya\"…", vListen: "Listening… go ahead", vThink: "Thinking…", vSpeak: "Speaking…", vNoSR: "Always-listening isn't supported in this browser. Press and hold the orb to talk.",
    wakeSub: "Listens only while the app is open on screen", freeTitle: "Free:", freeList: "video edits (10 a month), calls, WhatsApp messages, open apps/sites, songs, reminders, time, weather, short questions.", proTitle: "Pro:", proList: "unlimited edits, multi-step agent tasks, long research, account automation.",
    voiceHonest: "Divya listens only while the app is open on screen (a web app can't listen in the background). It can't call or send WhatsApp silently: it opens the dialer or WhatsApp with everything filled in, and you tap Call or Send. Speech recognition runs through the browser's service (Google in Chrome).",
    callBtn: n => `Call ${n}`, waBtn: "Open WhatsApp", openBtn: n => `Open ${n}`, playBtn: "Listen on YouTube", calBtn: "Add to Google Calendar", subBtn: "See plans", pickContact: "Pick from contacts", typeNumber: "Type number",
    noNumber: n => `I don't have ${n}'s number. Say "save ${n} 98xxxxxxxx", or pick from contacts.`, askNumber: n => `${n}'s phone number?`, saved: (n, x) => `Saved ${n} (+${x}). It stays on this phone only.`,
    remFire: t => `Reminder: ${t}`, notifTitle: "Divya reminder",
    connectNote: "Sign-in opens in your browser. Come back here when done.", connect: "Connect", connectedP: "Connected", soon: "Soon",
    setupIntro: "Divya sets up your own backend in YOUR accounts — only with your permission. For now: sign in with your email and add free API keys. Keys are encrypted and used only for your requests.",
    googleRow: "Continue with Google", googleSub: "Uses your email for setup", continueGoogle: "Continue",
    consent: "I allow Divya to save my keys encrypted and use them only for my requests.", guideBtn: "🔊 Voice-guided setup, step by step",
    needConsent: "Please tick the permission box first.", allow: "Allow", cancel: "Cancel", save: "Save", next: "Next step", done: "Done",
    stepNot: "Not set", stepOk: w => `Connected${w ? " · " + w : ""}`, stepFail: "Test failed", oneTap: "One-tap connect", openCreate: "Open & create key", pasteKey: "Paste key here", paste: "Paste", testSave: "Test & save", test: "Test", remove: "Remove", oauthSoon: "OAuth sign-in coming soon; paste a token for now.",
    foundKey: (n, l) => `Found a ${n} key (…${l}). Save it?`, keySaved: n => `${n} key saved and tested.`, keyBad: n => `That doesn't look like a ${n} key.`,
    guideStep: (n, d) => `${n} setup. ${d} I'll open the page. Sign in with your email, create a key, copy it, then come back to Divya.`, guideReturn: "Did you copy the key? Checking the clipboard.", guidePaste: "Paste the key in the box and tap Test and save.", guideDone: "All steps are done. Great!", guideNextQ: n => `Next: ${n}. Continue?`,
    serverTitle: "Your own server:", serverText: "With your Cloudflare token, Divya will deploy your own Worker in your account — coming soon (with your OK each time).", noPasswords: "Divya never stores passwords, never creates accounts silently, and never bypasses captchas. You sign in to each provider yourself.",
    d_openrouter: "Brain with free AI models (backup).", d_groq: "Fast brain + speech-to-text.", d_gemini: "Reads images and screenshots.", d_cloudflare: "For your own server (Worker).", d_github: "For the video machine (Actions).", d_huggingface: "For AI models and voices.",
    planNow: (p, u, l) => `Your plan: ${p === "premium" ? "Premium (owner/friend access)" : "Free"}. Video edits this month: ${l === null ? `${u} (no limit)` : `${u}/${l}`}.`,
    freePlan: "Free", f1: "Voice commands: call, WhatsApp, open apps, songs, reminders, time, weather", f2: "Chat & short questions", f3: "Voice-first mode for blind users", f4: "Use your own API keys",
    p1: "Unlimited video edits", p2: "Multi-step agent tasks, long research", p3: "Account automation (post/upload — with your OK)", priceSoon: "Price: soon", comingSoon: "Coming soon", noPayNote: "No payments yet. We'll tell you when Pro is ready.",
    installNow: "Install app", installed: "Divya is already installed as an app on this device ✓", canInstall: "One-tap install is available in this browser.", cantPrompt: "This browser doesn't show an install prompt — follow the steps below.", notApk: "This installs from your browser as an app (PWA). It's not a Play Store APK.",
    and1: "Open this page in Chrome.", and2: "Tap \"Install app\" above, or menu (⋮) → \"Install app\" / \"Add to Home screen\".", and3: "The Divya icon appears on your home screen.",
    ios1: "Open this page in Safari.", ios2: "Tap Share (□↑) → \"Add to Home Screen\".", ios3: "Tap \"Add\", then open Divya from your home screen.",
    pc1: "In Chrome/Edge, click the install icon (⊕ / monitor) in the address bar.", pc2: "Or menu → \"Install Divya\" / \"Apps → Install this site as an app\".",
    language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "When you speak, Divya answers aloud", voiceFirst: "Voice-first mode", voiceFirstSub: "Speaks every result and keeps listening after each answer (for blind users)", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts",
    netErr: "Network problem. Try again.", micDenied: "Allow microphone access in browser settings.", noRec: "Voice recording isn't supported in this browser.", loggedIn: n => `Logged in as ${n}`, orDone: "OpenRouter connected ✓", orFail: "OpenRouter didn't connect.",
  },
};
const t = (k, ...a) => { const v = (T[S.lang] || T.te)[k]; return typeof v === "function" ? v(...a) : v ?? k; };
function applyLang() {
  document.documentElement.lang = S.lang;
  $$("[data-t]").forEach(e => e.textContent = t(e.dataset.t));
  $$("[data-tp]").forEach(e => e.placeholder = t(e.dataset.tp));
  $$("[data-tl]").forEach(e => e.setAttribute("aria-label", t(e.dataset.tl)));
  $$("#setLang button").forEach(b => { b.classList.toggle("on", b.dataset.v === S.lang); b.setAttribute("aria-checked", b.dataset.v === S.lang); });
  if ($("#msgs .empty")) renderEmpty();
  if (S.token) { $("#me").textContent = t("loggedIn", whoAmI()); $("#drawerMe").textContent = whoAmI(); renderAcct(); renderAvatar(); if (cur === "profile") renderProfile(); if (S.quota) showQuota(S.quota.left, S.quota.limit, S.quota.used); }
  $("#greet").textContent = t("hello", new Date().getHours());
  if (cur) setTitle(cur);
  setVState(VA.state || "idle");
  renderSteps();
}
function applyTheme() {
  document.documentElement.dataset.theme = S.theme;
  $$("#setTheme button").forEach(b => { b.classList.toggle("on", b.dataset.v === S.theme); b.setAttribute("aria-checked", b.dataset.v === S.theme); });
  const dark = S.theme === "dark" || (S.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  $$('meta[name="theme-color"]').forEach(m => { m.removeAttribute("media"); m.content = dark ? "#000000" : "#ffffff"; });
}
function announce(msg) { const e = $("#sr"); e.textContent = ""; setTimeout(() => e.textContent = msg, 60); }
function toast(msg, say) { const e = $("#toast"); e.textContent = msg; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 3000); if (say || S.vf) speak(msg); }
function sheet(msg, btns) {
  $("#sheetText").textContent = msg; const box = $("#sheetBtns"); box.innerHTML = "";
  (btns || [{ label: "OK", primary: true }]).forEach(b => { const x = document.createElement("button"); x.className = "btn " + (b.primary ? "primary" : "secondary"); x.textContent = b.label; x.onclick = () => { $("#sheet").hidden = true; b.fn && b.fn(); }; box.appendChild(x); });
  $("#sheet").hidden = false; setTimeout(() => box.querySelector(".primary")?.focus(), 50);
  if (S.vf) speak(msg);
}
$$("[role=radiogroup] button").forEach(b => b.setAttribute("role", "radio"));

async function apiFetch(path, opts) {
  // try the remembered API host first, then the others; a TypeError means the host was unreachable (blocked, DNS, offline)
  const order = [API, ...API_BASES.filter(b => b !== API)]; let last;
  for (const base of order) {
    try { const r = await fetch(base + "/" + path, opts); if (base !== API) { API = base; localStorage.setItem("dv_apiIdx", String(API_BASES.indexOf(base))); } netState(true); return r; }
    catch (e) { last = e; }
  }
  netState(false); const err = new Error("net"); err.cause = last; throw err;
}
async function api(path, { method = "GET", json, form } = {}) {
  const h = {}; if (S.token) h.authorization = "Bearer " + S.token;
  let body; if (json) { h["content-type"] = "application/json"; body = JSON.stringify({ lang: S.lang, ...json }); } else if (form) body = form;
  const sep = path.includes("?") ? "&" : "?";
  const r = await apiFetch(path + (method === "GET" ? `${sep}lang=${S.lang}` : ""), { method, headers: h, body });
  const d = await r.json().catch(() => ({ ok: false, error: "bad response" }));
  if (r.status === 401 && !/^(login\/verify|auth\/|account\/(password|delete))/.test(path)) { logout(true); throw new Error("login"); }
  return { status: r.status, ...d };
}
/* network-blocked banner: shown when no API host answers */
function netState(ok) {
  $$(".net-banner").forEach(b => { b.hidden = ok; if (!ok) b.querySelector(".nb-text").textContent = navigator.onLine === false ? t("offline") : t("netBlocked"); });
}
async function netCheck() {
  for (const base of [API, ...API_BASES.filter(b => b !== API)]) {
    const c = new AbortController(), tm = setTimeout(() => c.abort(), 9000);
    try { const r = await fetch(base + "/health", { signal: c.signal, cache: "no-store" }); clearTimeout(tm); if (r.ok) { API = base; netState(true); return true; } } catch {} clearTimeout(tm);
  }
  netState(false); return false;
}
document.addEventListener("click", e => { if (e.target.closest("[data-retry]")) netCheck().then(ok => ok && toast("✓")); });
window.addEventListener("online", () => netCheck());

/* ---------- login ---------- */
const AUTH_FORMS = ["pwForm", "suForm", "numForm", "codeForm", "fgForm", "rsForm", "pvForm"];
let authTab = store.get("authTab", "pw");
function showForm(id, focus) {
  AUTH_FORMS.forEach(f => $("#" + f).hidden = f !== id); $("#loginErr").textContent = "";
  const tab = { pwForm: "pw", suForm: "su", numForm: "wa", codeForm: "wa" }[id];
  $("#authTabs").hidden = !tab;
  $$("#authTabs button").forEach(b => { const on = b.dataset.v === tab; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; });
  if (focus) setTimeout(() => $("#" + focus)?.focus(), 200);
}
function setTab(v, focus = true) { authTab = v; store.set("authTab", v); showForm({ pw: "pwForm", su: "suForm", wa: "numForm" }[v], focus ? { pw: "pwId", su: "suName", wa: "num" }[v] : null); }
$$("#authTabs button").forEach(b => b.onclick = () => setTab(b.dataset.v));
$("#authTabs").addEventListener("keydown", e => { if (!/Arrow(Left|Right)/.test(e.key)) return; const v = ["pw", "su", "wa"], i = v.indexOf(authTab); setTab(v[(i + (e.key === "ArrowRight" ? 1 : 2)) % 3], false); $("#tab-" + authTab).focus(); });
$$(".eye").forEach(b => b.onclick = () => { const i = b.parentElement.querySelector("input"); const show = i.type === "password"; i.type = show ? "text" : "password"; b.setAttribute("aria-pressed", show); });
function showLogin() { $("#main").hidden = true; $("#login").hidden = false; setTab(authTab, false); vaStop(); setTimeout(() => $({ pw: "#pwId", su: "#suName", wa: "#num" }[authTab]).focus(), 300); netCheck(); }
const whoAmI = () => S.number ? "+" + S.number : (S.acct?.email || "");
const normId = v => { v = v.trim(); return v.includes("@") ? v.toLowerCase() : v.replace(/[^\d+]/g, ""); };
function setSession(d) { S.token = d.token; S.number = d.number || ""; S.acct = d.account || S.acct || null; store.set("token", S.token); store.set("number", S.number); store.set("acct", S.acct); }
async function authCall(btn, path, json, onOk) {
  $("#loginErr").textContent = ""; btn.disabled = true;
  try { const d = await api(path, { method: "POST", json }); if (!d.ok) { $("#loginErr").textContent = (d.error || t("netErr")) + (d.tries_left > 0 && d.tries_left < 5 ? t("triesLeft", d.tries_left) : ""); if (S.vf) speak($("#loginErr").textContent); return d; } await onOk(d); return d; }
  catch (e) { $("#loginErr").textContent = e.message === "net" ? t("netBlockedT") : t("netErr"); }
  finally { btn.disabled = false; }
}
$("#pwForm").onsubmit = e => {
  e.preventDefault(); const id = normId($("#pwId").value), pw = $("#pwPass").value;
  if (!id) { $("#loginErr").textContent = t("needId"); return $("#pwId").focus(); } if (!pw) { $("#loginErr").textContent = t("needPw"); return $("#pwPass").focus(); }
  authCall($("#pwBtn"), "auth/login", { id, password: pw }, d => { $("#pwPass").value = ""; setSession(d); enter(); });
};
$("#suForm").onsubmit = e => {
  e.preventDefault();
  const json = { name: $("#suName").value.trim(), email: $("#suEmail").value.trim(), phone: $("#suPhone").value.replace(/[^\d+]/g, ""), password: $("#suPass").value };
  authCall($("#suBtn"), "auth/signup", json, d => {
    $("#suPass").value = ""; setSession(d);
    if (d.phone_status === "sent") { $("#pvSent").textContent = t("pvSentTo", "+" + d.account.phone_pending); showForm("pvForm", "pvCode"); return; }
    enter(); if (d.phone_msg) setTimeout(() => sheet(d.phone_msg), 400);
  }).then(d => { if (d && !d.ok && d.field) $("#su" + d.field[0].toUpperCase() + d.field.slice(1))?.focus(); });
};
$("#forgotBtn").onclick = () => { $("#fgId").value = $("#pwId").value; showForm("fgForm", "fgId"); };
$$("[data-back]").forEach(b => b.onclick = () => setTab("pw"));
$("#fgForm").onsubmit = e => {
  e.preventDefault(); const id = normId($("#fgId").value); if (!id) { $("#loginErr").textContent = t("needId"); return; }
  authCall($("#fgBtn"), "auth/forgot", { id }, d => { S.resetId = id; $("#rsSent").textContent = t("rsSentTo", d.to || ""); showForm("rsForm", "rsCode"); });
};
$("#rsForm").onsubmit = e => {
  e.preventDefault();
  authCall($("#rsBtn"), "auth/reset", { id: S.resetId, code: $("#rsCode").value, password: $("#rsPass").value }, d => { $("#rsPass").value = ""; $("#rsCode").value = ""; setSession(d); enter(); });
};
$("#pvForm").onsubmit = e => {
  e.preventDefault();
  authCall($("#pvBtn"), "account/phone/verify", { code: $("#pvCode").value }, d => { S.number = d.phone; store.set("number", S.number); toast(t("phoneLinked"), true); enter(); });
};
$("#pvSkip").onclick = () => enter();
["#pvCode", "#rsCode", "#lvCode"].forEach(sel => $(sel).addEventListener("input", e => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); }));
$("#numForm").onsubmit = async e => {
  e.preventDefault(); const n = $("#num").value.replace(/\D/g, "");
  if (n.length !== 10) { $("#loginErr").textContent = "10 digits"; return; }
  $("#numBtn").disabled = true; $("#loginErr").textContent = "";
  try {
    const d = await api("login/start", { method: "POST", json: { number: n } });
    if (!d.ok) { $("#loginErr").textContent = d.error || t("netErr"); return; }
    S.pendingNum = "91" + n; $("#codeSent").textContent = d.sent === false ? t("waitCode") : t("codeSentTo", "91" + n);
    showForm("codeForm", "code");
  } catch (e) { $("#loginErr").textContent = e.message === "net" ? t("netBlockedT") : t("netErr"); } finally { $("#numBtn").disabled = false; }
};
$("#code").oninput = e => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); if (e.target.value.length === 6) $("#codeForm").requestSubmit(); };
$("#codeForm").onsubmit = async e => {
  e.preventDefault(); $("#codeBtn").disabled = true; $("#loginErr").textContent = "";
  try {
    const d = await api("login/verify", { method: "POST", json: { number: S.pendingNum, code: $("#code").value } });
    if (!d.ok) { $("#loginErr").textContent = d.error || t("netErr"); $("#code").value = ""; return; }
    S.acct = null; setSession(d); enter();
  } catch (e) { $("#loginErr").textContent = e.message === "net" ? t("netBlockedT") : t("netErr"); } finally { $("#codeBtn").disabled = false; }
};
$("#changeNum").onclick = () => setTab("wa");
function logout(silent) {
  if (!silent && S.token) api("logout", { method: "POST", json: {} }).catch(() => {});
  S.token = ""; S.number = ""; S.acct = null; store.del("token"); store.del("number"); store.del("acct"); store.del("chat"); $("#msgs").innerHTML = ""; closeDrawer(); showLogin();
}

/* ---------- drawer + routing ---------- */
const ROUTES = ["home", "chat", "edit", "voice", "connect", "setup", "plan", "download", "settings", "profile"];
let cur = "";
function openDrawer() { $("#drawer").classList.add("open"); $("#drawer").inert = false; $("#drawerBg").hidden = false; $("#menuBtn").setAttribute("aria-expanded", "true"); $("#menuBtn").setAttribute("aria-label", t("closeMenu")); setTimeout(() => $("#drawer a[aria-current=page]")?.focus() || $("#drawer a")?.focus(), 60); }
function closeDrawer(focusBack) { $("#drawer").classList.remove("open"); $("#drawer").inert = true; $("#drawerBg").hidden = true; $("#menuBtn").setAttribute("aria-expanded", "false"); $("#menuBtn").setAttribute("aria-label", t("openMenu")); if (focusBack) $("#menuBtn").focus(); }
$("#menuBtn").onclick = () => $("#drawer").classList.contains("open") ? closeDrawer(true) : openDrawer();
$("#drawerBg").onclick = () => closeDrawer(true);
document.addEventListener("keydown", e => { if (e.key === "Escape") { if (!$("#sheet").hidden) $("#sheet").hidden = true; else if ($("#drawer").classList.contains("open")) closeDrawer(true); } });
$("#drawer").addEventListener("click", e => { if (e.target.closest("a")) closeDrawer(); });
$("#drawerLogout").onclick = () => logout(false);
function setTitle(name) { const s = $("#s-" + name); $("#screen-title").textContent = t(s.dataset.title); document.title = `${t(s.dataset.title)} · Divya`; }
function route() {
  if ($("#main").hidden) return;
  let name = (location.hash.match(/^#\/(\w+)/) || [])[1]; if (name === "create") name = "edit"; if (!ROUTES.includes(name)) name = "home";
  const first = !cur; if (name === cur) return; cur = name;
  $$("#screens .screen").forEach(s => s.classList.toggle("active", s.id === "s-" + name));
  $$("#drawer a[data-r], #tabbar a[data-r]").forEach(a => a.dataset.r === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  name === "profile" ? $("#avatarBtn").setAttribute("aria-current", "page") : $("#avatarBtn").removeAttribute("aria-current");
  setTitle(name);
  if (!first) { $("#screen-title").focus({ preventScroll: true }); }
  announce(t("screen", t($("#s-" + name).dataset.title)));
  if (S.vf && !first && VA.state !== "speak") speak(t("screen", t($("#s-" + name).dataset.title)));
  if (name === "connect" || name === "settings") loadConnect();
  if (name === "edit" || name === "home") loadStatus();
  if (name === "profile") { renderProfile(); loadPlan(); loadConnect(); }
  if (name === "setup") { loadKeys(); loadConnect(); }
  if (name === "plan" || name === "home") loadPlan();
  if (name === "download") renderDownload();
  if (name === "chat") scrollDown();
}
window.addEventListener("hashchange", route);
const go = name => { location.hash = "#/" + name; };

/* ---------- speech out ---------- */
let voices = []; const loadVoices = () => voices = speechSynthesis?.getVoices() || [];
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
function speak(text) {
  return new Promise(res => {
    if (!("speechSynthesis" in window) || !text) return res();
    const clean = String(text).replace(/https?:\/\/\S+/g, "").replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "").replace(/[✓•…]/g, " ").trim(); if (!clean) return res();
    const u = new SpeechSynthesisUtterance(clean); const telugu = /[\u0C00-\u0C7F]/.test(clean);
    const want = telugu ? ["te-IN"] : ["en-IN", "hi-IN", "en-GB", "en-US"];
    const fem = /female|heera|veena|neerja|swara|kalpana|zira|samantha|google/i;
    let v = null; for (const l of want) { const c = voices.filter(x => x.lang.replace("_", "-") === l); v = c.find(x => fem.test(x.name)) || c[0]; if (v) break; }
    if (v) { u.voice = v; u.lang = v.lang; } else u.lang = telugu ? "te-IN" : "en-IN";
    u.rate = 1; u.pitch = 1.05; let done = false; const fin = () => { if (!done) { done = true; res(); } };
    u.onend = fin; u.onerror = fin; setTimeout(fin, Math.min(30000, 1500 + clean.length * 90));
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  });
}
function chime(up = true) {
  try {
    const C = window.AudioContext || window.webkitAudioContext; if (!C) return; chime.c = chime.c || new C(); const c = chime.c; const n = c.currentTime;
    [[up ? 660 : 880, 0], [up ? 990 : 590, .11]].forEach(([f, d]) => { const o = c.createOscillator(), g = c.createGain(); o.type = "sine"; o.frequency.value = f; g.gain.setValueAtTime(0, n + d); g.gain.linearRampToValueAtTime(.18, n + d + .02); g.gain.exponentialRampToValueAtTime(.001, n + d + .22); o.connect(g).connect(c.destination); o.start(n + d); o.stop(n + d + .25); });
  } catch {}
}

/* ---------- contacts (local only) + actions ---------- */
const contacts = () => store.get("contacts", {});
function findContact(name) { if (!name) return ""; const c = contacts(); const k = name.toLowerCase().trim(); if (c[k]) return c[k]; const hit = Object.keys(c).find(x => x.includes(k) || k.includes(x)); return hit ? c[hit] : ""; }
function saveContact(name, num) { const c = contacts(); c[name.toLowerCase().trim()] = num; store.set("contacts", c); }
function normNum(s) { const d = String(s || "").replace(/\D/g, ""); if (d.length < 7) return ""; return d.length === 10 ? "91" + d : d; }
function localCommand(text) {
  let m = text.match(/^(?:save|సేవ్)\s+(.+?)\s+(?:number\s+|నంబర్\s+)?(\+?[\d\s-]{10,})\s*(?:save\s*(?:cheyyi|chey)?)?$/i) || text.match(/^(.+?)\s+number\s+(\+?[\d\s-]{10,})\s+save\s*(?:cheyyi|chey)?$/i);
  if (m) { const n = normNum(m[2]); if (n) { saveContact(m[1], n); return { reply: t("saved", m[1], n) }; } }
  if (pendingContact && /\d{10}/.test(text.replace(/\D/g, ""))) { const n = normNum(text); const p = pendingContact; pendingContact = null; saveContact(p.name, n); return { reply: t("saved", p.name, n), action: { ...p.action, number: n } }; }
  return null;
}
let pendingContact = null;
function openUrl(url) {
  if (store.get("noauto", false)) return;
  if (/^(tel:|intent:)/.test(url)) { location.href = url; return; }
  const w = window.open(url, "_blank", "noopener"); if (!w) location.href = url;
}
function ytUrl(q) { const web = "https://www.youtube.com/results?search_query=" + encodeURIComponent(q); return isAndroid ? `intent://www.youtube.com/results?search_query=${encodeURIComponent(q)}#Intent;scheme=https;package=com.google.android.youtube;S.browser_fallback_url=${encodeURIComponent(web)};end` : web; }
function calUrl(at, text) { const f = d => new Date(d).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); return "https://calendar.google.com/calendar/render?" + new URLSearchParams({ action: "TEMPLATE", text, dates: `${f(at)}/${f(at + 15 * 60000)}`, details: "Divya reminder" }); }
/* returns {buttons, auto(), say} ; buttons rendered as links/buttons for screen readers */
function planAction(a) {
  const out = { buttons: [], auto: null, say: "" };
  if (!a) return out;
  if (a.type === "call") {
    const num = a.number || findContact(a.name); const who = a.name || ("+" + num);
    if (num) { out.buttons.push({ label: t("callBtn", who), href: "tel:+" + num }); out.auto = () => openUrl("tel:+" + num); }
    else { pendingContact = { name: a.name, action: a }; out.say = t("noNumber", a.name); addContactButtons(out, a); }
  } else if (a.type === "whatsapp") {
    const num = a.number || findContact(a.name); const url = `https://wa.me/${num || ""}?text=${encodeURIComponent(a.text || "")}`;
    out.buttons.push({ label: t("waBtn"), href: url }); out.auto = () => openUrl(url);
    if (!num && a.name) addContactButtons(out, a, true);
  } else if (a.type === "open") { out.buttons.push({ label: t("openBtn", new URL(a.url).hostname.replace(/^www\./, "")), href: a.url }); out.auto = () => openUrl(a.url); }
  else if (a.type === "play") { const u = ytUrl(a.query || ""); out.buttons.push({ label: t("playBtn"), href: u }); out.auto = () => openUrl(u); }
  else if (a.type === "reminder") { addReminder(a.at, a.text); out.buttons.push({ label: t("calBtn"), href: calUrl(a.at, a.text), alt: true }); }
  else if (a.type === "subscribe") out.buttons.push({ label: t("subBtn"), href: "#/plan" });
  else if (a.type === "route" && ROUTES.includes(a.to)) { out.buttons.push({ label: t(a.to === "edit" ? "sEdit" : "sHome"), href: "#/" + a.to }); out.auto = () => go(a.to); }
  return out;
}
function addContactButtons(out, a, alt) {
  if (navigator.contacts?.select) out.buttons.push({ label: t("pickContact"), alt: true, fn: async () => { try { const [c] = await navigator.contacts.select(["name", "tel"], { multiple: false }); const n = normNum(c?.tel?.[0]); if (n) { saveContact(a.name, n); pendingContact = null; runAction({ ...a, number: n }, true); } } catch {} } });
  out.buttons.push({ label: t("typeNumber"), alt: true, fn: () => { const v = prompt(t("askNumber", a.name)); const n = normNum(v); if (n) { saveContact(a.name, n); pendingContact = null; runAction({ ...a, number: n }, true); } } });
}
function runAction(a, auto) { const p = planAction(a); if (auto && p.auto) p.auto(); return p; }
function renderButtons(box, btns) {
  btns.forEach(b => {
    const el = document.createElement(b.href ? "a" : "button"); el.className = "act-btn" + (b.alt ? " alt" : ""); el.textContent = b.label;
    if (b.href) { el.href = b.href; if (!b.href.startsWith("#")) { el.target = "_blank"; el.rel = "noopener"; } } else el.onclick = b.fn;
    box.appendChild(el);
  });
}

/* reminders: in-app timers (only while open) + calendar link */
const remTimers = {};
function addReminder(at, text) { const l = store.get("rem", []).filter(r => r.at > Date.now()); if (!l.some(r => r.at === at)) l.push({ at, text }); store.set("rem", l); schedule(); if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {}); }
function schedule() {
  store.get("rem", []).forEach(r => {
    if (remTimers[r.at] || r.at < Date.now() - 60000) return;
    remTimers[r.at] = setTimeout(() => {
      chime(false); navigator.vibrate?.([200, 100, 200]); const msg = t("remFire", r.text); toast(msg, true);
      try { if (Notification.permission === "granted") navigator.serviceWorker?.ready.then(reg => reg.showNotification(t("notifTitle"), { body: r.text, icon: "icon-192.png" })); } catch {}
      store.set("rem", store.get("rem", []).filter(x => x.at !== r.at));
    }, Math.max(0, r.at - Date.now()));
  });
}

/* ---------- chat ---------- */
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const linkify = s => esc(s).replace(/https?:\/\/[^\s<]+/g, u => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
function scrollDown() { const m = $("#msgs"); requestAnimationFrame(() => m.scrollTop = m.scrollHeight); }
function bubble(role, text, extra = {}) {
  $("#msgs .empty")?.remove();
  const d = document.createElement("div"); d.className = "msg " + (role === "user" ? "me" : role === "sys" ? "sys" : "bot");
  if (extra.img) { const i = new Image(); i.src = extra.img; i.alt = "image"; d.appendChild(i); if (text) { const p = document.createElement("div"); p.textContent = text; d.appendChild(p); } }
  else d.innerHTML = (extra.heard ? `<span class="heard" aria-hidden="true">🎙️</span>` : "") + linkify(text);
  if (extra.buttons?.length) { const box = document.createElement("div"); box.className = "act"; renderButtons(box, extra.buttons); d.appendChild(box); }
  $("#msgs").appendChild(d); scrollDown(); return d;
}
function typing(on) {
  $("#msgs .typing")?.remove();
  if (on === true) { const d = document.createElement("div"); d.className = "msg bot typing"; d.setAttribute("aria-label", t("thinking")); d.innerHTML = "<i></i><i></i><i></i>"; $("#msgs").appendChild(d); scrollDown(); }
}
function renderEmpty() {
  const m = $("#msgs"); m.innerHTML = "";
  const e = document.createElement("div"); e.className = "empty";
  e.innerHTML = `<img src="icon-192.png" alt=""><h2>${esc(t("emptyTitle"))}</h2><div class="muted">${esc(t("emptySub"))}</div><div class="chips">${["s1", "s2", "s3"].map(k => `<button class="chip">${esc(t(k))}</button>`).join("")}</div>`;
  e.querySelectorAll(".chip").forEach(c => c.onclick = () => send(c.textContent));
  m.appendChild(e);
}
function saveChat() { store.set("chat", $$("#msgs .msg:not(.typing):not(.sys)").slice(-40).map(e => ({ r: e.classList.contains("me") ? "user" : "assistant", c: e.querySelector("img") ? "[image]" : (e.firstChild?.nodeType === 3 || !e.querySelector(".act") ? e.textContent : [...e.childNodes].filter(n => !(n.classList && n.classList.contains("act"))).map(n => n.textContent).join("")) }))); }
async function loadHistory() {
  const cached = store.get("chat", null);
  const draw = list => { if (!list.length) return renderEmpty(); $("#msgs").innerHTML = ""; list.forEach(x => bubble(x.r, x.c)); };
  if (cached) draw(cached);
  try {
    const d = await api("history");
    if (d.ok) { const list = d.messages.filter(m => m.content).map(m => ({ r: m.role, c: m.content.replace(/^\[screenshot\] /, "🖼️ ").replace(/^\[app\] /, "") })); if (!cached || list.length) { draw(list); saveChat(); } }
  } catch {}
}
let coords = store.get("coords", null);
function getCoords() { return new Promise(res => { if (!navigator.geolocation) return res(null); navigator.geolocation.getCurrentPosition(p => { coords = { lat: p.coords.latitude, lon: p.coords.longitude, at: Date.now() }; store.set("coords", coords); res(coords); }, () => res(null), { timeout: 8000, maximumAge: 3600000 }); }); }
async function assist(text) {
  const local = localCommand(text); if (local) return { ok: true, local: true, ...local };
  const c = coords && Date.now() - coords.at < 86400000 ? coords : null;
  let d = await api("assist", { method: "POST", json: { text, tz, ...(c ? { lat: c.lat, lon: c.lon } : {}) } });
  if (d.need === "location") { const g = await getCoords(); if (g) d = await api("assist", { method: "POST", json: { text, tz, lat: g.lat, lon: g.lon } }); }
  return d;
}
let busy = false;
async function send(text) {
  text = (text || "").trim(); if (!text || busy) return;
  busy = true; bubble("user", text); $("#input").value = ""; autoGrow(); updateBtn(); typing(true);
  try {
    const d = await assist(text); typing(false);
    if (!d.ok && !d.reply) bubble("bot", d.error || t("netErr"));
    else { const p = runAction(d.action, true); bubble("bot", d.reply + (p.say ? "\n" + p.say : ""), { buttons: p.buttons }); if (S.vf) speak(d.reply + (p.say ? " " + p.say : "")); if (d.video_started) toast(t("started")); }
  } catch (e) { typing(false); if (e.message !== "login") bubble("sys", t("netErr")); }
  busy = false; saveChat();
}
const input = $("#input");
function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
function updateBtn() { const has = !!input.value.trim(); $("#micSend").classList.toggle("send", has); $("#micSend").classList.toggle("mic", !has); }
input.addEventListener("input", () => { autoGrow(); updateBtn(); });
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && matchMedia("(pointer:fine)").matches) { e.preventDefault(); send(input.value); } });
$("#composer").onsubmit = e => { e.preventDefault(); send(input.value); };

/* image */
$("#attach").onclick = () => $("#file").click();
$("#file").onchange = async e => {
  const f = e.target.files[0]; e.target.value = ""; if (!f || busy) return;
  const small = await shrink(f); const url = URL.createObjectURL(small);
  const q = input.value.trim(); input.value = ""; autoGrow(); updateBtn();
  busy = true; bubble("user", q, { img: url }); typing(true);
  const fd = new FormData(); fd.append("image", small, "image.jpg"); fd.append("lang", S.lang); if (q) fd.append("q", q);
  try { const d = await api("image", { method: "POST", form: fd }); typing(false); bubble("bot", d.reply || d.error || t("netErr")); if (S.vf) speak(d.reply || ""); }
  catch (er) { typing(false); if (er.message !== "login") bubble("sys", t("netErr")); }
  busy = false; saveChat();
};
function shrink(file) {
  return new Promise(res => {
    const img = new Image(); img.onload = () => {
      const m = 1600, k = Math.min(1, m / Math.max(img.width, img.height)); const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      c.toBlob(b => res(b || file), "image/jpeg", 0.85);
    }; img.onerror = () => res(file); img.src = URL.createObjectURL(file);
  });
}

/* ---------- push-to-talk recorder (chat mic + orb fallback) ---------- */
let rec, chunks = [], recStart = 0, recTimer, stream, recTarget = "chat";
function pickMime() { for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) if (window.MediaRecorder && MediaRecorder.isTypeSupported?.(m)) return m; return ""; }
async function startRec(btn, target) {
  if (busy) return; recTarget = target;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return toast(t("noRec"), true);
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch { return toast(t("micDenied"), true); }
  if (!btn.pressed) { stream.getTracks().forEach(x => x.stop()); return; }
  speechSynthesis?.cancel(); vaPause();
  const mime = pickMime(); rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); chunks = [];
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  rec.onstop = onRecStop; rec.start(); recStart = Date.now();
  btn.classList.add("recording"); if (target === "chat") $("#recBar").hidden = false; else setVState("listen");
  navigator.vibrate?.(15);
  recTimer = setInterval(() => { const s = Math.floor((Date.now() - recStart) / 1000); $("#recTime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; if (s >= 120) stopRec(btn); }, 250);
}
function stopRec(btn) { clearInterval(recTimer); btn.classList.remove("recording"); $("#recBar").hidden = true; $("#recTime").textContent = "0:00"; if (rec && rec.state !== "inactive") rec.stop(); }
async function onRecStop() {
  stream?.getTracks().forEach(x => x.stop());
  const dur = Date.now() - recStart;
  if (dur < 600) { toast(t("holdMic"), true); if (recTarget !== "chat") setVState(vaIdleState()); return; }
  const type = rec.mimeType || "audio/webm"; const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
  const blob = new Blob(chunks, { type });
  const fd = new FormData(); fd.append("audio", blob, "voice." + ext); fd.append("lang", S.lang); fd.append("assist", "1"); fd.append("tz", tz);
  if (coords) { fd.append("lat", coords.lat); fd.append("lon", coords.lon); }
  busy = true;
  if (recTarget === "chat") {
    const me = bubble("user", "🎙️ …"); typing(true);
    try {
      const d = await api("voice", { method: "POST", form: fd }); typing(false);
      if (d.heard) { me.innerHTML = `<span class="heard" aria-hidden="true">🎙️</span>` + linkify(d.heard); const p = runAction(d.action, true); bubble("bot", (d.reply || d.error || "") + (p.say ? "\n" + p.say : ""), { buttons: p.buttons }); if (S.voice || S.vf) speak((d.reply || "") + " " + (p.say || "")); if (d.video_started) toast(t("started")); }
      else { me.remove(); bubble("sys", d.error || t("netErr")); }
    } catch (e) { typing(false); me.remove(); if (e.message !== "login") bubble("sys", t("netErr")); }
    busy = false; saveChat();
  } else {
    setVState("think");
    try { const d = await api("voice", { method: "POST", form: fd }); busy = false; if (d.heard) await vaShow(d.heard, d); else { $("#vReply").textContent = d.error || t("netErr"); speak(d.error || t("netErr")); setVState(vaIdleState()); } }
    catch (e) { busy = false; setVState(vaIdleState()); }
  }
}
function holdable(btn, target, isSendable) {
  btn.addEventListener("pointerdown", e => { if (isSendable && btn.classList.contains("send")) return; if (target === "voice" && SR) return; e.preventDefault(); btn.pressed = true; btn.setPointerCapture?.(e.pointerId); startRec(btn, target); });
  const up = () => { if (!btn.pressed) return; btn.pressed = false; if (rec && rec.state === "recording") stopRec(btn); };
  btn.addEventListener("pointerup", up); btn.addEventListener("pointercancel", up);
  btn.addEventListener("contextmenu", e => e.preventDefault());
}
const micBtn = $("#micSend");
holdable(micBtn, "chat", true);
micBtn.addEventListener("click", () => { if (micBtn.classList.contains("send")) send(input.value); });
// keyboard / screen-reader double-tap on the chat mic: start voice assistant listening instead of hold
micBtn.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && micBtn.classList.contains("mic")) { e.preventDefault(); go("voice"); setTimeout(() => vaOnce(), 300); } });

/* ---------- "Hey Divya" voice assistant ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const WAKE = /\b(?:hey|hi|hay|he|ok|okay|ఓకే|హే|హాయ్)[\s,]*(?:divya|diviya|divyaa|dhivya|divia|దివ్య|దివ్యా)\b|(?:హే|హాయ్)\s*దివ్యా?/i;
const VA = { on: false, state: "idle", r: null, cmdTimer: 0, once: false, followUp: false };
function setVState(s) {
  VA.state = s; const o = $("#orb"); if (o) o.dataset.state = s;
  const txt = { idle: SR ? t("vIdle") : t("vNoSR"), wake: t("vWake"), listen: t("vListen"), think: t("vThink"), speak: t("vSpeak") }[s] || "";
  $("#vState").textContent = txt; $("#wakeDot").hidden = !(VA.on && s === "wake");
}
const vaIdleState = () => VA.on ? "wake" : "idle";
function vaKill() { if (VA.r) { VA.r.onend = null; VA.r.onresult = null; VA.r.onerror = null; try { VA.r.abort(); } catch {} VA.r = null; } clearTimeout(VA.cmdTimer); }
function vaListen(mode) {
  if (!SR || document.hidden || $("#main").hidden) return;
  vaKill(); const r = new SR(); VA.r = r;
  r.lang = S.lang === "en" ? "en-IN" : "te-IN"; r.continuous = true; r.interimResults = true; r.maxAlternatives = 1;
  setVState(mode);
  if (mode === "listen") VA.cmdTimer = setTimeout(() => { if (VA.state === "listen") { vaKill(); VA.followUp = false; if (VA.on) vaListen("wake"); else setVState("idle"); } }, VA.followUp ? 7000 : 9000);
  r.onresult = e => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i], txt = res[0].transcript.trim();
      if (VA.state === "wake") {
        const m = txt.match(WAKE);
        if (m) { const after = txt.slice(m.index + m[0].length).replace(/^[\s,.!]+/, ""); chime(); if (res.isFinal && after.length > 1) return vaCommand(after); setVState("listen"); clearTimeout(VA.cmdTimer); VA.cmdTimer = setTimeout(() => { if (VA.state === "listen") setVState("wake"); }, 8000); $("#vHeard").textContent = after; }
      } else if (VA.state === "listen") {
        const clean = txt.replace(WAKE, "").replace(/^[\s,.!]+/, "");
        $("#vHeard").textContent = clean;
        if (res.isFinal && clean.length > 1) return vaCommand(clean);
      }
    }
  };
  r.onerror = e => { if (e.error === "not-allowed" || e.error === "service-not-allowed") { VA.on = false; store.set("wake", false); $("#wakeToggle").checked = false; setVState("idle"); toast(t("micDenied"), true); } };
  r.onend = () => { if (VA.r !== r) return; VA.r = null; if (document.hidden) return; if (VA.state === "wake" && VA.on) setTimeout(() => VA.on && VA.state === "wake" && !VA.r && vaListen("wake"), 300); else if (VA.state === "listen") setTimeout(() => VA.state === "listen" && !VA.r && vaListen("listen"), 200); };
  try { r.start(); } catch {}
}
async function vaCommand(text) {
  vaKill(); VA.followUp = false; setVState("think"); $("#vHeard").textContent = "“" + text + "”"; $("#vReply").textContent = ""; $("#vActions").innerHTML = "";
  if (cur !== "voice") go("voice");
  try { const d = await assist(text); await vaShow(text, d); }
  catch (e) { $("#vReply").textContent = t("netErr"); await speak(t("netErr")); vaAfter(); }
}
async function vaShow(heard, d) {
  $("#vHeard").textContent = "“" + heard + "”";
  const p = runAction(d.action, true); const reply = (d.reply || d.error || t("netErr")) + (p.say ? " " + p.say : "");
  $("#vReply").textContent = reply; $("#vActions").innerHTML = ""; renderButtons($("#vActions"), p.buttons);
  if (d.video_started) toast(t("started"));
  setVState("speak"); await speak(reply); vaAfter();
}
function vaAfter() { if (document.hidden) { setVState(vaIdleState()); return; } if (S.vf && SR) { VA.followUp = true; chime(); vaListen("listen"); } else if (VA.on) vaListen("wake"); else setVState("idle"); }
function vaOnce() { if (!SR) { toast(t("vNoSR"), true); return; } speechSynthesis?.cancel(); chime(); $("#vReply").textContent = ""; $("#vHeard").textContent = ""; $("#vActions").innerHTML = ""; vaListen("listen"); }
function vaStart() { if (!SR) { setVState("idle"); return; } VA.on = true; store.set("wake", true); $("#wakeToggle").checked = true; if (VA.state !== "listen" && VA.state !== "think" && VA.state !== "speak") vaListen("wake"); }
function vaStop() { VA.on = false; store.set("wake", false); $("#wakeToggle").checked = false; vaKill(); setVState("idle"); }
function vaPause() { vaKill(); }
$("#wakeToggle").onchange = e => e.target.checked ? vaStart() : vaStop();
$("#orbBtn").addEventListener("click", () => { if (!SR) return; if (VA.state === "listen") { vaKill(); setVState(vaIdleState()); if (VA.on) vaListen("wake"); } else vaOnce(); });
holdable($("#orbBtn"), "voice", false);
$("#heyBtn").onclick = () => { go("voice"); setTimeout(() => SR ? vaOnce() : toast(t("vNoSR"), true), 250); };
$("#avatarBtn").onclick = () => go("profile");
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { vaKill(); if (VA.state !== "idle") setVState(vaIdleState()); }
  else if (S.token && !$("#main").hidden) { if (VA.on) vaListen("wake"); if (guide.id) guideReturn(); if (cur === "connect" || cur === "setup") loadConnect(); }
});

/* ---------- edit (the user's own video) ---------- */
$$(".seg[data-name] button").forEach(b => b.onclick = () => { b.parentElement.querySelectorAll("button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); }); });
$$(".seg button").forEach(b => b.setAttribute("aria-checked", b.classList.contains("on")));
const ED = { src: "upload", kind: "" };
$$("#srcSeg button").forEach(b => { b.setAttribute("role", "radio"); b.onclick = () => { ED.src = b.dataset.v; $$("#srcSeg button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); }); $("#srcUploadBox").hidden = ED.src !== "upload"; $("#srcLinkBox").hidden = ED.src !== "link"; $("#srcHelp").dataset.t = ED.src === "upload" ? "uploadHelp" : "linkHelp"; $("#srcHelp").textContent = t($("#srcHelp").dataset.t); if (ED.src === "link") $("#videoUrl").focus(); }; });
$$("#kindSeg button").forEach(b => b.onclick = () => { ED.kind = b.dataset.v; $$("#kindSeg button").forEach(x => x.setAttribute("aria-checked", x === b)); });
$("#kindSeg").addEventListener("keydown", e => { if (!/Arrow(Up|Down|Left|Right)/.test(e.key)) return; e.preventDefault(); const bs = $$("#kindSeg button"), i = Math.max(0, bs.findIndex(x => x.dataset.v === ED.kind)), n = bs[(i + (/Down|Right/.test(e.key) ? 1 : bs.length - 1)) % bs.length]; n.click(); n.focus(); });
$("#videoFile").onchange = () => { const f = $("#videoFile").files[0]; $("#fileName").textContent = f ? `${f.name} · ${(f.size / 1048576).toFixed(1)} MB` : t("pickVideo"); $("#editErr").textContent = f && f.size > 24 * 1048576 ? t("tooBig") : ""; };
function xhrUpload(path, form, onProg) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest(); x.open("POST", API + "/" + path); x.setRequestHeader("authorization", "Bearer " + S.token);
    x.upload.onprogress = e => e.lengthComputable && onProg(Math.round(e.loaded / e.total * 100));
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch {} if (x.status === 401) { logout(true); return rej(new Error("login")); } res({ status: x.status, ...d }); };
    x.onerror = () => { netState(false); rej(new Error("net")); }; x.send(form);
  });
}
$("#editForm").onsubmit = async e => {
  e.preventDefault(); const err = $("#editErr"); err.textContent = "";
  const pick = n => $(`.seg[data-name=${n}] .on`).dataset.v, f = $("#videoFile").files[0], link = $("#videoUrl").value.trim();
  if (ED.src === "upload" ? !f : !link) { err.textContent = t("needSrc"); return (ED.src === "upload" ? $("#videoFile") : $("#videoUrl")).focus(); }
  if (ED.src === "upload" && f.size > 24 * 1048576) { err.textContent = t("tooBig"); return; }
  if (!ED.kind) { err.textContent = t("needKind"); return $("#kindSeg button").focus(); }
  const fields = { kind: ED.kind, language: pick("language"), length: pick("length"), notes: $("#editNotes").value.trim(), lang: S.lang };
  $("#editBtn").disabled = true;
  try {
    let d;
    if (ED.src === "upload") {
      const fd = new FormData(); Object.entries(fields).forEach(([k, v]) => fd.append(k, v)); fd.append("video", f, f.name);
      $("#upProg").hidden = false; d = await xhrUpload("edit", fd, p => { $("#upBar").style.width = p + "%"; $("#editBtn").textContent = t("uploading", p); });
    } else d = await api("edit", { method: "POST", json: { ...fields, url: link } });
    if (d.ok) { toast(t("started"), true); $("#videoFile").value = ""; $("#fileName").textContent = t("pickVideo"); $("#videoUrl").value = ""; $("#editNotes").value = ""; setTimeout(loadStatus, 800); loadPlan(); }
    else { err.textContent = d.error || t("netErr"); if (d.busy) loadStatus(); if (S.vf) speak(err.textContent); }
  } catch (x) { if (x.message !== "login") err.textContent = x.message === "net" ? t("netBlockedT") : t("netErr"); }
  finally { $("#editBtn").disabled = false; $("#editBtn").textContent = t("editBtn"); $("#upProg").hidden = true; $("#upBar").style.width = "0"; }
};
let lastJob = null;
function setJob(kind, when, job) {
  lastJob = job || null;
  const title = kind ? t(kind === "queued" ? "jobQueued" : kind === "run" ? "jobRun" : kind === "done" ? "jobDone" : "jobFail") : t("noJob");
  let sub = kind ? t(job ? (kind === "done" ? "jobDoneSub2" : kind === "fail" ? "jobFailSub2" : "jobRunSub2") : (kind === "done" ? "jobDoneSub" : kind === "fail" ? "jobFailSub" : "jobRunSub")) : t("noJobSub");
  if (job && job.note && kind !== "done") sub = job.note + " · " + sub;
  if (when) sub += " · " + when;
  const cls = "pulse" + (kind === "done" ? " done" : kind === "fail" ? " fail" : kind ? "" : " idle");
  $("#jobCard").hidden = !kind; $("#jobDot").className = cls; $("#jobTitle").textContent = title; $("#jobSub").textContent = sub;
  $("#homeJobDot").className = cls; $("#homeJobTitle").textContent = title; $("#homeJobSub").textContent = sub;
  $("#dlBtn").hidden = !(job && job.has_result);
}
$("#dlBtn").onclick = async () => {
  if (!lastJob) return; $("#dlBtn").disabled = true;
  try {
    const r = await apiFetch("result?job=" + lastJob.job, { headers: { authorization: "Bearer " + S.token } });
    if (!r.ok) { toast(t("netErr"), true); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = url; a.download = `divya-edit-${lastJob.job}.mp4`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch { toast(t("netErr"), true); } finally { $("#dlBtn").disabled = false; }
};
function showQuota(left, limit, used) {
  S.quota = { left, limit, used };
  $("#homeQuotaNum").textContent = limit === null || limit === undefined ? "∞" : left;
  $("#homeQuotaSub").textContent = limit === null || limit === undefined ? t("unlimitedSub") : t("quotaSub", used, limit);
  $("#editQuota").textContent = t("editsLine", left, limit ?? null);
  $("#profEdits").textContent = limit === null || limit === undefined ? t("unlimited") : `${left}/${limit}`;
}
let statusTimer;
async function loadStatus() {
  clearTimeout(statusTimer);
  try {
    const d = await api("status"); if (!d.ok) return;
    if ("edits_limit" in d) showQuota(d.edits_left, d.edits_limit, d.edits_used);
    const ago = ts => { const m = Math.max(0, Math.round((Date.now() - new Date(ts)) / 60000)); return m < 60 ? `${m} min` : `${Math.round(m / 60)} h`; };
    const j = d.job, r = d.runs?.[0]; let active = false;
    if (j) { const k = j.state === "done" ? "done" : j.state === "failed" ? "fail" : j.state === "queued" ? "queued" : "run"; active = k === "queued" || k === "run"; setJob(k, ago(j.upd || j.at), j); }
    else if (d.busy || (r && r.status !== "completed")) { active = true; setJob("run", r ? ago(r.created_at) : ""); }
    else if (r) setJob(r.conclusion === "success" ? "done" : "fail", ago(r.updated_at));
    else setJob(null);
    if ((cur === "edit" || cur === "home") && active) statusTimer = setTimeout(loadStatus, 10000);
  } catch {}
}
/* ---------- profile ---------- */
function initials() { const n = S.acct?.name || ""; return n ? n.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase() : ""; }
function renderAvatar() { const i = initials(); ["#avatarTop", "#avatarBig"].forEach(sel => { const el = $(sel); if (i) el.textContent = i; else if (!el.querySelector("svg")) el.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>'; }); $("#avatarBtn").setAttribute("aria-label", t("openProfile") + (S.acct?.name ? ": " + S.acct.name : "")); }
function renderProfile() {
  renderAvatar(); const a = S.acct;
  $("#profName").textContent = a?.name || (S.number ? "+" + S.number : "Divya");
  $("#profSub").textContent = a ? (a.email || "") : t("waLogin");
  $("#profEmail").textContent = a?.email || "—";
  $("#profPhone").textContent = S.number ? "+" + S.number + " ✓" : a?.phone_pending ? "+" + a.phone_pending + " (" + t("notVerified") + ")" : "—";
  $("#profPlan").textContent = S.plan === "premium" ? t("planPrem") : S.plan ? t("planFree") : "…";
  if (S.quota) showQuota(S.quota.left, S.quota.limit, S.quota.used);
  renderAcct();
}
$("#profLogout").onclick = () => logout(false);

/* ---------- connect ---------- */
const PDESC = { te: { youtube: "Videos upload cheyadaniki", google: "Gmail, Drive", instagram: "Reels post cheyadaniki", facebook: "Page lo post cheyadaniki", telegram: "Telegram lo kuda Divya" }, en: { youtube: "Upload videos", google: "Gmail, Drive", instagram: "Post Reels", facebook: "Post to your Page", telegram: "Divya on Telegram too" } };
let connData = [];
async function connectLink(prov) {
  const w = window.open("about:blank", "_blank");
  const r = await api("connect/link", { method: "POST", json: { provider: prov } }).catch(() => ({}));
  if (r.ok && r.url) { if (w) w.location = r.url; else location.href = r.url; } else { w?.close(); toast(r.error || t("netErr")); }
}
async function loadConnect() {
  try {
    const d = await api("connect"); if (!d.ok) return; connData = d.providers;
    $("#connCount").textContent = $("#profConn").textContent = `${d.providers.filter(p => p.connected).length}/${d.providers.length}`;
    $("#provList").innerHTML = d.providers.map(p => `<div class="row"><div class="prov"><div class="pi" aria-hidden="true">${esc(p.name[0])}</div><div class="pt"><b>${esc(p.name)}</b><span class="muted small">${esc(p.connected ? (p.who || t("connectedP")) : (PDESC[S.lang]?.[p.id] || p.desc))}</span></div></div>
      ${p.connected ? `<span class="pill ok">✓ ${t("connectedP")}</span>` : p.ready ? `<button class="pill go" data-p="${p.id}" aria-label="${esc(t("connect") + " " + p.name)}">${t("connect")}</button>` : `<span class="pill wait">${t("soon")}</span>`}</div>`).join("");
    $$("#provList [data-p]").forEach(b => b.onclick = () => connectLink(b.dataset.p));
    const g = d.providers.find(p => p.id === "google");
    if (g) { $("#gWho").textContent = g.connected ? (g.who || t("connectedP")) : t("googleSub"); $("#gBtn").hidden = !!g.connected || !g.ready; }
  } catch {}
}
$("#gBtn").onclick = () => connectLink("google");

/* ---------- server & API setup ---------- */
const CF_TPL = "https://dash.cloudflare.com/profile/api-tokens?" + new URLSearchParams({ permissionGroupKeys: JSON.stringify([{ key: "workers_scripts", type: "edit" }, { key: "workers_kv_storage", type: "edit" }, { key: "account_settings", type: "read" }]), name: "Divya", accountId: "*", zoneId: "all" });
const KP = {
  openrouter: { name: "OpenRouter", oauth: true, rx: /^sk-or-v1-[a-f0-9]{40,}$/i, url: "https://openrouter.ai/settings/keys" },
  groq: { name: "Groq", rx: /^gsk_[A-Za-z0-9]{20,}$/, url: "https://console.groq.com/keys" },
  gemini: { name: "Gemini", rx: /^AIza[0-9A-Za-z_-]{30,}$/, url: "https://aistudio.google.com/app/apikey" },
  cloudflare: { name: "Cloudflare", rx: /^[A-Za-z0-9_-]{40}$/, url: CF_TPL },
  github: { name: "GitHub", soon: true, rx: /^(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})$/, url: "https://github.com/settings/tokens/new?scopes=repo,workflow&description=Divya" },
  huggingface: { name: "Hugging Face", soon: true, rx: /^hf_[A-Za-z0-9]{30,}$/, url: "https://huggingface.co/settings/tokens/new?tokenType=read&tokenName=Divya" },
};
let keyState = {};
async function loadKeys() { try { const d = await api("keys"); if (d.ok) { keyState = Object.fromEntries(d.providers.map(p => [p.id, p])); renderSteps(); } } catch {} }
function renderSteps() {
  const box = $("#steps"); if (!box) return; $("#consent").checked = S.consent;
  box.innerHTML = Object.entries(KP).map(([id, k]) => {
    const s = keyState[id] || {}; const st = s.set ? (s.ok ? t("stepOk", s.who) : t("stepFail")) : t("stepNot");
    return `<li class="step${s.set && s.ok ? " done" : ""}" id="st-${id}"><div class="step-h"><b>${esc(k.name)}</b><span class="pill wait">${esc(st)}</span></div>
      <p class="muted small">${esc(t("d_" + id))}${k.soon ? " " + esc(t("oauthSoon")) : ""}</p>
      <div class="btns">${k.oauth ? `<button class="act-btn" data-or>${esc(t("oneTap"))}</button>` : ""}<a class="act-btn${k.oauth ? " alt" : ""}" href="${esc(k.url)}" target="_blank" rel="noopener" data-open="${id}">${esc(t("openCreate"))}</a>
      ${s.set ? `<button class="act-btn alt" data-test="${id}">${esc(t("test"))}</button><button class="act-btn alt" data-del="${id}">${esc(t("remove"))}</button>` : ""}</div>
      <div class="keyrow"><label class="sr-only" for="key-${id}">${esc(k.name + " " + t("pasteKey"))}</label><input class="keyfield" id="key-${id}" type="password" autocomplete="off" spellcheck="false" placeholder="${esc(t("pasteKey"))}" data-key="${id}">
      <button class="act-btn alt" data-paste="${id}" aria-label="${esc(t("paste") + " " + k.name)}">${esc(t("paste"))}</button><button class="act-btn" data-save="${id}" aria-label="${esc(t("testSave") + " " + k.name)}">${esc(t("testSave"))}</button></div></li>`;
  }).join("");
  box.querySelectorAll("[data-or]").forEach(b => b.onclick = orConnect);
  box.querySelectorAll("[data-save]").forEach(b => b.onclick = () => saveKey(b.dataset.save, $("#key-" + b.dataset.save).value.trim()));
  box.querySelectorAll("[data-paste]").forEach(b => b.onclick = async () => { try { const v = (await navigator.clipboard.readText()).trim(); $("#key-" + b.dataset.paste).value = v; checkPasted(b.dataset.paste, v); } catch { $("#key-" + b.dataset.paste).focus(); toast(t("guidePaste"), true); } });
  box.querySelectorAll("[data-key]").forEach(i => i.addEventListener("input", () => checkPasted(i.dataset.key, i.value.trim())));
  box.querySelectorAll("[data-test]").forEach(b => b.onclick = async () => { const d = await api("keys/test", { method: "POST", json: { provider: b.dataset.test } }).catch(() => ({})); toast(d.ok ? t("stepOk", d.who) : (d.error || t("netErr")), true); loadKeys(); });
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { await api("keys/delete", { method: "POST", json: { provider: b.dataset.del } }).catch(() => {}); loadKeys(); });
}
$("#consent").onchange = e => { S.consent = e.target.checked; store.set("consent", S.consent); };
function needConsent(then) { if (S.consent) return true; sheet(t("needConsent"), [{ label: t("allow"), primary: true, fn: () => { S.consent = true; store.set("consent", true); $("#consent").checked = true; then && then(); } }, { label: t("cancel") }]); return false; }
function checkPasted(id, v) { if (v && KP[id].rx.test(v)) confirmKey(id, v); }
function confirmKey(id, v) {
  if (confirmKey.open === v) return; confirmKey.open = v;
  sheet(t("foundKey", KP[id].name, v.slice(-4)), [{ label: t("save"), primary: true, fn: () => { confirmKey.open = ""; saveKey(id, v); } }, { label: t("cancel"), fn: () => { confirmKey.open = ""; } }]);
}
async function saveKey(id, v) {
  if (!v) { $("#key-" + id)?.focus(); return; }
  if (!needConsent(() => saveKey(id, v))) return;
  if (!KP[id].rx.test(v) && v.length < 16) { toast(t("keyBad", KP[id].name), true); return; }
  const d = await api("keys/save", { method: "POST", json: { provider: id, key: v, consent: true } }).catch(() => ({}));
  if (d.ok) { toast(t("keySaved", KP[id].name), true); if (guide.id === id) { guide.id = ""; await loadKeys(); return guideNext(true); } }
  else toast(d.error || t("netErr"), true);
  loadKeys();
}
async function orConnect() {
  if (!needConsent(orConnect)) return;
  const v = [...crypto.getRandomValues(new Uint8Array(48))].map(b => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"[b % 64]).join("");
  const dig = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v)));
  const ch = btoa(String.fromCharCode(...dig)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  store.set("orv", v);
  location.href = "https://openrouter.ai/auth?" + new URLSearchParams({ callback_url: location.host === new URL(APP_URL).host ? APP_URL + "/setup" : BASE + "?orcb=1", code_challenge: ch, code_challenge_method: "S256" });
}
async function orFinish() {
  const code = store.get("orcode", ""), v = store.get("orv", ""); if (!code || !v) { store.del("orcode"); return; }
  store.del("orcode"); store.del("orv");
  const d = await api("keys/openrouter", { method: "POST", json: { code, verifier: v } }).catch(() => ({}));
  toast(d.ok ? t("orDone") : (d.error || t("orFail")), true); loadKeys();
}
/* voice-guided setup: speak each step, open the page, read the clipboard on return, one confirmation to save */
const guide = { id: "" };
$("#guideBtn").onclick = () => { if (needConsent(() => guideNext())) guideNext(); };
async function guideNext(afterSave) {
  await loadKeys();
  const id = Object.keys(KP).find(k => !(keyState[k]?.set && keyState[k]?.ok));
  if (!id) { guide.id = ""; toast(t("guideDone"), true); return; }
  if (afterSave) return sheet(t("guideNextQ", KP[id].name), [{ label: t("next"), primary: true, fn: () => guideOpen(id) }, { label: t("done") }]);
  guideOpen(id);
}
function guideOpen(id) {
  guide.id = id; $("#st-" + id)?.scrollIntoView({ block: "center" });
  speak(t("guideStep", KP[id].name, t("d_" + id)));
  if (KP[id].oauth) return orConnect();
  window.open(KP[id].url, "_blank", "noopener");
}
async function guideReturn() {
  const id = guide.id; if (!id || KP[id].oauth) return;
  try { const v = (await navigator.clipboard.readText()).trim(); if (KP[id].rx.test(v)) { $("#key-" + id).value = v; return confirmKey(id, v); } } catch {}
  $("#key-" + id)?.focus(); speak(t("guidePaste"));
}

/* ---------- plan ---------- */
async function loadPlan() { try { const d = await api("plan"); if (d.ok) { S.plan = d.plan; $("#planNow").textContent = t("planNow", d.plan, d.edits_used, d.edits_limit); showQuota(d.edits_left, d.edits_limit, d.edits_used); if (cur === "profile") renderProfile(); } } catch {} }

/* ---------- download / install ---------- */
let deferred = null; const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; renderDownload(); });
window.addEventListener("appinstalled", () => { deferred = null; renderDownload(); });
function renderDownload() {
  const st = $("#dlStatus"), b = $("#installBtn");
  if (standalone()) { st.textContent = t("installed"); b.hidden = true; return; }
  b.hidden = false; st.textContent = deferred ? t("canInstall") : t("cantPrompt");
}
$("#installBtn").onclick = async () => {
  if (deferred) { deferred.prompt(); await deferred.userChoice.catch(() => {}); deferred = null; renderDownload(); }
  else sheet(isIOS ? `${t("ios1")}\n${t("ios2")}\n${t("ios3")}` : isAndroid ? `${t("and1")}\n${t("and2")}` : `${t("pc1")}\n${t("pc2")}`);
};

/* ---------- account (email/phone + password users) ---------- */
function renderAcct() {
  const a = S.acct, card = $("#acctCard"); card.hidden = !a; if (!a) return;
  $("#acctInfo").textContent = `${a.name} · ${a.email}`;
  $("#phoneInfo").textContent = a.phone ? t("phoneOk", "+" + a.phone) : a.phone_pending ? t("phonePend", "+" + a.phone_pending) : t("phoneNone");
  $("#lpForm").hidden = !!a.phone; if (a.phone) $("#lvForm").hidden = true;
  if (!$("#lpPhone").value && a.phone_pending) $("#lpPhone").value = a.phone_pending.replace(/^91(?=\d{10}$)/, "");
}
async function acctCall(btn, path, json, onOk) {
  $("#acctErr").textContent = ""; btn.disabled = true;
  try { const d = await api(path, { method: "POST", json }); if (!d.ok) { $("#acctErr").textContent = d.error || t("netErr"); if (S.vf) speak($("#acctErr").textContent); return; } await onOk(d); }
  catch (e) { if (e.message !== "login") $("#acctErr").textContent = e.message === "net" ? t("netBlockedT") : t("netErr"); }
  finally { btn.disabled = false; }
}
$("#lpForm").onsubmit = e => { e.preventDefault(); acctCall($("#lpBtn"), "account/phone", { phone: $("#lpPhone").value.replace(/[^\d+]/g, "") }, d => { if (d.status === "linked") return; $("#phoneInfo").textContent = t("pvSentTo", d.to); $("#lvForm").hidden = false; $("#lvCode").focus(); }); };
$("#lvForm").onsubmit = e => { e.preventDefault(); acctCall($("#lvBtn"), "account/phone/verify", { code: $("#lvCode").value }, d => { S.number = d.phone; S.acct = { ...S.acct, phone: d.phone, phone_pending: "" }; store.set("number", S.number); store.set("acct", S.acct); $("#lvCode").value = ""; applyLang(); toast(t("phoneLinked"), true); }); };
$("#delOpen").onclick = () => { $("#delForm").hidden = !$("#delForm").hidden; if (!$("#delForm").hidden) $("#delPass").focus(); };
$("#delForm").onsubmit = e => { e.preventDefault(); acctCall($("#delBtn"), "account/delete", { password: $("#delPass").value }, () => { $("#delPass").value = ""; $("#delForm").hidden = true; toast(t("deleted"), true); logout(true); }); };
async function refreshMe() { try { const d = await api("me"); if (d.ok) { S.number = d.number || ""; S.acct = d.account || null; store.set("number", S.number); store.set("acct", S.acct); applyLang(); } } catch {} }

/* ---------- settings ---------- */
$$("#setLang button").forEach(b => b.onclick = () => { S.lang = b.dataset.v; store.set("lang", S.lang); applyLang(); loadConnect(); if (VA.r) vaListen(VA.state); });
$$("#setTheme button").forEach(b => b.onclick = () => { S.theme = b.dataset.v; store.set("theme", S.theme); applyTheme(); });
$("#setVoice").onchange = e => { S.voice = e.target.checked; store.set("voice", S.voice); };
$("#setVF").onchange = e => { S.vf = e.target.checked; store.set("vf", S.vf); if (S.vf) { S.voice = true; store.set("voice", true); $("#setVoice").checked = true; speak(t("voiceFirst") + " on"); } };
$("#logout").onclick = () => logout(false);
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);

/* ---------- boot ---------- */
function enter() {
  $("#login").hidden = true; $("#main").hidden = false; $("#me").textContent = t("loggedIn", whoAmI()); $("#drawerMe").textContent = whoAmI(); renderAcct(); refreshMe();
  loadHistory(); loadConnect(); loadKeys(); schedule(); cur = "";
  route(); setTimeout(() => $("#screen-title").focus({ preventScroll: true }), 50);
  if (store.get("orcode", "")) { go("setup"); orFinish(); }
  if (S.wake && SR) vaStart();
}
// OpenRouter PKCE callback lands on /setup?code=...
if (location.pathname.endsWith("/setup") || new URLSearchParams(location.search).has("orcb")) { const c = new URLSearchParams(location.search).get("code"); if (c) store.set("orcode", c); history.replaceState(null, "", BASE + "#/setup"); }
applyTheme(); applyLang(); $("#setVoice").checked = S.voice; $("#setVF").checked = S.vf; $("#wakeToggle").checked = S.wake && !!SR; $("#wakeToggle").disabled = !SR; updateBtn(); setJob(null); setVState("idle");
if (S.token) { enter(); netCheck(); } else showLogin();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
