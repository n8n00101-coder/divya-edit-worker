"use strict";
// API hosts, tried in order; the first that answers is remembered. Add a second host here (e.g. a custom domain) if *.workers.dev is blocked.
const API_BASES = ["https://divya.n8n00101.workers.dev/api"];
let API = API_BASES[Math.min(parseInt(localStorage.getItem("dv_apiIdx") || "0", 10) || 0, API_BASES.length - 1)];
const APP_URL = "https://divya-app.n8n00101.workers.dev";
// App version — KEEP IN SYNC with sw.js `const V`. checkUpdate() compares the live
// sw.js file against this so a phone can never stay stuck on a stale cached shell.
const APP_V = "divya-v26";
const BASE = new URL(".", location.href.split("#")[0].split("?")[0].replace(/\/setup$/, "/")).href; // works at / and at /divya-edit-worker/app/
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const store = { get: (k, d) => { try { const v = localStorage.getItem("dv_" + k); return v === null ? d : JSON.parse(v); } catch { return d; } }, set: (k, v) => localStorage.setItem("dv_" + k, JSON.stringify(v)), del: k => localStorage.removeItem("dv_" + k) };
const S = { token: store.get("token", ""), number: store.get("number", ""), acct: store.get("acct", null), lang: store.get("lang", "en"), voice: store.get("voice", true), vf: store.get("vf", false), blind: store.get("blind", false), theme: store.get("theme", "auto"), wake: store.get("wake", false), consent: store.get("consent", false), voiceId: store.get("voiceId", "f-adult-priya") };
const isAndroid = /android/i.test(navigator.userAgent), isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const tz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata"; } catch { return "Asia/Kolkata"; } })();

/* ---------- text ---------- */
// Indian units for token display: 1 lakh = 100,000; 1 crore = 10,000,000.
function fmtTok(n) { n = Math.round(+n || 0); if (n >= 1e7) return (n / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " crore"; if (n >= 1e5) return (n / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " lakh"; return n.toLocaleString("en-IN"); }
const T = {
  te: {
    skip: "Content ki vellu", numLabel: "WhatsApp number", codeLabel: "6 ankela code",
    loginSub: "Nee WhatsApp number ivvu. Code WhatsApp ki vasthundi.", loginSub2: "Nee personal AI. Login avvu leda kotha account create cheyyi.", loginWays: "Login vidhanam", tabLogin: "Login", tabSignup: "Sign up", tabWa: "WhatsApp code",
    idLabel: "Email leda phone number", idPh: "Email leda phone number", pwLabel: "Password", newPwLabel: "Password (kanisam 8)", nameLabel: "Nee peru", emailLabel: "Email", phoneLabel: "Phone (WhatsApp) — optional", showPw: "Password chupinchu",
    logIn: "Login", forgot: "Password marchipoyava?", createAcct: "Account create cheyyi", suHint: "Phone WhatsApp code tho verify ayyaka matrame link avuthundi. Kotha accounts Free plan lo untayi.",
    forgotT: "Password reset", forgotSub: "Nee email leda verified phone ivvu. Reset code nee verified WhatsApp ki vasthundi.", sendResetCode: "Reset code pampu", backLogin: "Login ki venakki", setPw: "Kotha password set cheyyi", rsSentTo: n => `${n} ki WhatsApp lo code pampa.`,
    verifyPhoneT: "Phone verify", pvSentTo: n => `${n} ki WhatsApp lo 6 ankela code pampa.`, later: "Tarvatha", needId: "Email leda phone ivvu.", needPw: "Password ivvu.", need10: "10 ankela number ivvu.", triesLeft: n => ` (${n} tries migilayi)`,
    netBlockedT: "Divya server ki connect avvaledu.", netBlocked: "Nee network (ISP) *.workers.dev ni block chestundochu. Mobile data ↔ Wi-Fi marchi chudu, leda Private DNS (1.1.1.1 / dns.google) on cheyyi.", offline: "Internet ledu. Connection chusi malli try cheyyi.", retry: "Malli try cheyyi",
    account: "Account", phoneOk: n => `Phone: ${n} ✓ verified`, phoneNone: "Phone link avvaledu. Link chesthe phone tho login + password reset vasthayi.", phonePend: n => `Phone ${n}: inka verify avvaledu.`, sendCode: "Code pampu", phoneLinked: "Phone link ayyindi ✓", delAcct: "Account delete cheyyi", delWarn: "Nee account, login, app chat history delete avuthayi. Password tho confirm cheyyi.", delConfirm: "Delete confirm", deleted: "Account delete ayyindi.", getCode: "Code pampu", verify: "Login", codeHint: "Code raakapothe WhatsApp lo Divya ki \"login\" ani pampu.", changeNum: "Number marchu", codeSentTo: n => `+${n} ki WhatsApp lo code pampa.`, waitCode: "Code already pampa. WhatsApp chudu.",
     sProfile: "Profile", tHome: "Home", tVoice: "Voice", tChat: "Chat", tSetup: "Setup", tPlan: "Plan", tabsLabel: "Main tabs", openProfile: "Profile open cheyyi",
    editsLeftT: "Free shorts migilinavi", notVerified: "verify kaaledu", quotaSub: (u, l) => `Ee varam ${u}/${l} shorts vaadavu · Monday ki reset`, unlimited: "Unlimited", unlimitedSub: "Owner/friend — limit ledu",
        tooBig: "Ee file 24 MB kante pedda. 24 MB lopu video attach cheyyi.", attachVideoMsg: "Ee video ni chat lo edit cheyyi", attachChatNote: "Chat lo edit avthundhi",
    editsLine: (left, l) => l === null ? "Unlimited shorts (owner/friend)" : `Ee varam ${left}/${l} free shorts migilayi`,
    jobQueued: "Edit queue lo undi", jobRunSub2: "Konchem time paduthundi. Ready ayyaka ikkade download vasthundi.", jobDoneSub2: "Download cheyyi (3 rojulu untundi).", jobFailSub2: "Ee edit nee free count lo lekka ledu. Link/file chusi malli try cheyyi.",
    email: "Email", phone: "Phone", planL: "Plan", planFree: "Free", planPrem: "Premium (owner/friend)", waLogin: "WhatsApp login", f0: "Varam ki 5 shorts (free)",
    openMenu: "Menu open cheyyi", closeMenu: "Menu close cheyyi", menu: "Main menu", heyDivya: "Hey Divya — matladu", quickActions: "Shortcuts",
    sHome: "Home", sChat: "Chat", sVoice: "Voice assistant", sConnect: "Accounts connect", sSetup: "Server & API setup", sPlan: "Subscription", sDownload: "App download", sSettings: "Settings", logout: "Logout",
    gChat: "Chat", gVoice: "Voice", gConnect: "Connect", gSetup: "Server setup", gPlan: "Plan", gDownload: "Download", gSettings: "Settings",
    screen: n => `${n} screen`,
    hello: h => h < 12 ? "నమస్కారం, good morning" : h < 17 ? "నమస్కారం, good afternoon" : "నమస్కారం, good evening", greetSub: "Ee roju em cheddam?", heySub: "Tap chesi matladu: call, WhatsApp, open, songs, reminders",
    noJob: "Edit emi ledu", noJobSub: "Chat lo topic cheppu — Divya video create chesthundi.",
    online: "Online", thinking: "Typing…", listening: "Vintunna…", releaseToSend: "Vadilithe pamputha", typeMsg: "Message…", bubblePh: "Divya tho matladu…", holdMic: "Mic ni press chesi pattuko, matladu, vadilai.", holdToTalk: "Press chesi pattukoni matladu, leda message pampu", attachImage: "Image / video pampu",
    emptyTitle: "Hi, nenu Divya", emptySub: "Chat cheyyi, matladu, leda pani cheppu.", s1: "YouTube open cheyyi", s2: "Ippudu time entha?", s3: "Nuvvu em cheyagalavu?",
    length: "Length",
    jobRun: "Edit jarugutondi", jobRunSub: "Konchem time paduthundi. Ready ayyaka ikkade pampistha.", jobDone: "Edit ready ✓", jobDoneSub: "Chat lo chudu.", jobFail: "Edit fail ayyindi", jobFailSub: "Malli try cheyyi.", started: "Video start chesa! Ready ayyaka ikkade pampistha.",
    tapToTalk: "Tap chesi matladu", vIdle: "Tap chesi matladu", vWake: "\"Hey Divya\" kosam vintunna…", vListen: "Vintunna… cheppu", vThink: "Alochistunna…", vSpeak: "Cheptunna…", vNoSR: "Ee browser lo always-listening ledu. Orb ni press chesi pattukoni matladu.",
    wakeSub: "App screen meeda open unnantha sepu vintundi", freeTitle: "Free:", freeList: "5 shorts a week (free), calls, WhatsApp message, apps/sites open, songs, reminders, time, weather, chinna questions.", proTitle: "Pro:", proList: "unlimited shorts, multi-step agent pani, long research, account automation.",
    voiceHonest: "Divya app open ga, screen meeda unnappude vintundi (web app background lo vinadu). Call/WhatsApp silent ga pampadu: dialer leda WhatsApp ni anni fill chesi open chestundi, nuvvu Call/Send nokkali. Voice recognition browser service (Chrome lo Google) dwara jarugutundi.",
    callBtn: n => `Call ${n}`, waBtn: "WhatsApp open cheyyi", openBtn: n => `${n} open cheyyi`, playBtn: "YouTube lo vinu", openedTab: n => `${n} open chesa — kottha tab lo`, openedApp: n => `${n} open chesa`, openYTApp: "YouTube app open chesa ✓", ytNoApp: "YouTube app phone lo ledu — browser lo open chesa.", ytOpening: "YouTube app open chesthunna…", waApp: "WhatsApp app open chesa ✓", waNoApp: "WhatsApp app phone lo ledu — browser lo open chesa.", waOpening: "WhatsApp app open chesthunna…", updBanner: v => `Kotha version ${v} vachindi — Refresh cheyyi.`, updRefresh: "Refresh cheyyi", updCheck: "App update check cheyyi", updLatest: "App latest version lo undi ✓", openBlocked: "Browser open cheyanivvaledu — kindha link tap cheyyi", openOff: "Auto-open off lo undi — kindha link tap cheyyi", calBtn: "Google Calendar lo add cheyyi", subBtn: "Plans chudu", pickContact: "Contacts nunchi select", typeNumber: "Number type cheyyi",
    noNumber: n => `${n} number naa daggara ledu. "save ${n} 98xxxxxxxx" ani cheppu, leda contacts nunchi select cheyyi.`, askNumber: n => `${n} phone number?`, saved: (n, x) => `${n} number save chesa (+${x}). Ee phone lo matrame untundi.`,
    remFire: t => `Reminder: ${t}`, notifTitle: "Divya reminder",
    connectNote: "Login page browser lo open avuthundi. Connect ayyaka ikkadiki tirigi raa.", connect: "Connect", connectedP: "Connected", soon: "Tvaralo",
    setupIntro: "Divya ni nee sontha accounts lo setup chestham — Groq, OpenRouter, Gemini (free AI keys) + Cloudflare (nee server). Divya anni chesthundhi — accounts, API keys, server setup — nee okka allow tho. Neeku emi cheyalsina pani undadhu.",
    googleRow: "Continue with Google", googleSub: "Nee email ni setup ki vaadutham", continueGoogle: "Continue", orLoginPw: "Leda password tho login cheyyi",
    consent: "Naa keys ni Divya encrypt chesi save chesi, naa requests kosam matrame vaadadaniki permission istunna.", guideBtn: "🔊 Voice tho manual setup",
    needConsent: "Mundu permission box tick cheyyi.", allow: "Allow", cancel: "Cancel", save: "Save", next: "Next step", done: "Ayyindi", delData: "Naa data delete cheyyi", delDataConfirm: "Nee account, chats, tokens — anni delete avthayi. Ee action ni venakki theeyalem. Confirm cheyala?", delDataDone: "Nee data delete chesam.", templateLabel: "Style template",
    stepNot: "Inka ledu", stepOk: w => `Connected${w ? " · " + w : ""}`, stepFail: "Test fail", oneTap: "One-tap connect", openCreate: "Open & key create", pasteKey: "Key ikkada paste cheyyi", paste: "Paste", testSave: "Test & save", test: "Test", remove: "Remove", oauthSoon: "OAuth login tvaralo; ippudu token paste cheyyi.",
    foundKey: (n, l) => `${n} key dorikindi (…${l}). Save cheyyana?`, keySaved: n => `${n} key save ayyindi, test pass.`, keyBad: n => `Idi ${n} key laaga ledu.`,
    guideStep: (n, d) => `${n} manual step. ${d} Nee daggara key unte ikkada paste cheyyi — leda one-tap setup tho Divya anni chesthundhi.`, guideReturn: "Key copy chesava? Clipboard nunchi chustunna.", guidePaste: "Key ni box lo paste chesi Test & save nokku.", guideDone: "Anni steps ayyayi. Super!", guideNextQ: n => `Next: ${n}. Continue cheyyana?`,
    serverTitle: "Nee sontha server:", serverText: "Cloudflare server kuda Divya ne setup chesthundhi — nee okka allow tho. Neeku emi cheyalsina pani undadhu.",
    d_openrouter: "Free AI models tho brain (backup).", d_groq: "Fast brain + voice-to-text.", d_gemini: "Images/screenshots chadavadaniki.", d_cloudflare: "Nee sontha server (Worker) kosam.", d_github: "Video machine (Actions) kosam.", d_huggingface: "AI models/voices kosam.",
    planNow: (p, u, l) => `Nee plan: ${p === "premium" ? "Premium (owner/friend access)" : "Free"}. Ee varam shorts: ${l === null ? `${u} (limit ledu)` : `${u}/${l}`}.`,
    freePlan: "Free", f1: "Voice commands: call, WhatsApp, open apps, songs, reminders, time, weather", f2: "Chat & chinna questions", f3: "Blind users kosam voice-first mode", f4: "Nee sontha API keys vaadochu",
    p1: "Unlimited video edits", p2: "Multi-step agent pani, long research", p3: "Account automation (post/upload — nee OK tho)", priceSoon: "Price: tvaralo", comingSoon: "Tvaralo vasthundi", noPayNote: "Ippudu payments levu. Pro ready ayyaka cheptham.",
    installNow: "App install cheyyi", installed: "Divya ee device lo already app laaga install ayyindi ✓", canInstall: "Ee browser lo one-tap install undi.", cantPrompt: "Ee browser auto install chupinchadu — kinda steps follow avvu.", notApk: "Idi browser nunchi app laaga install avuthundi (PWA). Play Store APK kaadu.",
    and1: "Chrome lo ee page open cheyyi.", and2: "Paina \"App install cheyyi\" nokku, leda menu (⋮) → \"Install app\" / \"Add to Home screen\".", and3: "Home screen lo Divya icon vasthundi.",
    ios1: "Safari lo ee page open cheyyi.", ios2: "Share (□↑) nokku → \"Add to Home Screen\".", ios3: "\"Add\" nokku. Home screen nunchi open cheyyi.",
    pc1: "Chrome/Edge address bar lo install icon (⊕ / monitor) nokku.", pc2: "Leda menu → \"Install Divya\" / \"Apps → Install this site as an app\".",
    language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "Mic lo adigithe Divya gattiga reply chestundi", voiceFirst: "Voice-first mode", voiceFirstSub: "Prathi result gattiga cheptundi, answer tarvatha malli vintundi (blind users kosam)", blindMode: "Blind Mode", blindModeSub: "Anni voice tho — pedha buttons, high contrast, captcha guide, voice signup", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts",
    inviteTitle: "Friends ni invite cheyyi", inviteSub: "Okkaru join aithe iddariki 10 lakh tokens (10 shorts leda 1× 10-min video). Pool tokens expire avvavu.", copy: "Copy", redeem: "Redeem", inviteStatus: (i, e) => `${i} invites · ${e} tokens vachayi`, tokSub: (w, p, v, d) => `Week lo ${fmtTok(w)} tokens migilayi · pool ${fmtTok(p)} · ${v} shorts · reset ${d}`, voiceSignup: "Voice tho signup cheyyi", voiceIncluded: "Voice assistant included — anni plans lo", capDone: "Captcha solve chesa ✓", capNo: "Sare, solve cheyaledu.", capAskShot: "Captcha screenshot pampu, nenu chadivi answer cheptha.", blindHello: "Blind Mode on. Anni voice tho cheptha. Em cheyyali?",
    netErr: "Network problem. Malli try cheyyi.", micDenied: "Mic permission ivvu (browser settings lo).", noRec: "Ee browser lo voice record avvadu.", loggedIn: n => `${n} tho login`, orDone: "OpenRouter connect ayyindi ✓", orFail: "OpenRouter connect avvaledu.",
    voicePick: "Voice (Divya gonthu)", voiceLoading: "Voices load avthunnayi… (modati sari ~90 MB download)", voiceReady: "Voices ready ✓ (Kokoro)", voiceLoadFail: "Voices load avvaledhu — internet check chesi malli try cheyyi. Ippudu system voice tho matladthunna.", voiceRetry: "Voices malli load cheyyi", voiceRetryNote: "Kokoro load avvaledhu — ippudu phone system voice matrame play avthundhi, andhuke anni voices okela vinipisthayi.", voicePlayedSystem: l => `Ee voice Kokoro kadhu — phone system voice (${l}) tho play ayyindhi. Kokoro load ayyaka selected voice vintundhi.`, voiceNoVoice: "Voice play avvaledhu — Kokoro load avvaledhu, phone lo voice kuda ledu. Internet check cheyyi.", voiceSample: "Hi, nenu Divya. Ee voice tho matladutha.", vChild: "Pillalu", vTeen: "Teenage", vAdult: "30–60", vElder: "60+ peddalu", vFemale: "Female", vMale: "Male", gsAsk: "Setup cheyala? Divya anni setup chesthundhi — accounts, API keys, server — neeku emi cheyalsina pani undadhu.", gsDeclined: "Sare, setup cheyaledu. Chat panichesthundi — setup kavali ante Setup screen lo eppudaina start cheyochu.", gsStopped: "Sare, ikkada aapesthunna. Setup screen lo continue cheyochu.", gsVerifyAsk: "Verification mail vachindhi — link ni okkasari tap cheyu, migilina anni nene chestha.", sPost: "YouTube post", postIntro: "Edit chesina video ni YouTube lo post cheyyi. Title, description, tags ivvu, schedule kuda set cheyochu.", postVideo: "Video (job id leda link)", postJobPh: "Job id leda video link", postTitle: "Title", postDesc: "Description", postTags: "Tags (comma tho)", postTagsPh: "divya, ai, video", postPrivacy: "Privacy", postSchedule: "Schedule (optional)", postThumb: "Thumbnail (optional)", postBtn: "YouTube lo post cheyyi", postDone: "Post ayyindi ✓", postViews: "Views", postLikes: "Likes", postComments: "Comments", postNeedVideo: "Video job id leda link ivvu.", sHistory: "Naa videos", gHistory: "Naa videos", histIntro: "Edit ayina videos — video 1, video 2 ani numbers. Upload cheyataniki chat lo 'upload video 1' ani cheppu.", histEmpty: "Inka videos levu. Chat lo video attach cheyyi.", histWatch: "Chudu / Download", histUpload: "Upload cheyu", histDone: "Ready", histFail: "Fail ayyindi", histEditing: "Edit avthondi",
    setupOneTap: "One-tap setup start cheyyi (okka allow)", setupConsent: "Okka allow tho Divya anni chesthundhi — accounts create cheyyadam, API keys theeskovadam, captchas solve cheyyadam, server setup — anni Divya ne chesthundhi. Neeku emi cheyalsina pani undadhu.", setupHowT: "Setup ela work avthundhi?", setupHowDivyaT: "Divya chesthundhi:", setupHowDivya: "accounts create cheyyadam, API keys theeskovadam, captchas solve cheyyadam, Cloudflare server setup cheyyadam — anni Divya ne chesthundhi, nee okka allow tho.", setupHowYouT: "Neeku okkasari matrame:", setupHowAfterT: "Tarvatha:", setupHowAfter: "setup ayyaka Divya chat lo neeku chepthundhi — appudu nunchi Divya nee accounts tho panichesthundi.", setupHowNote: "Divya anni chesthundhi — nee allow tho. Email link tap / SMS code thappa, neeku emi cheyalsina pani undadhu.", setupStepNote: "Kindha prathi step ki state untundhi: Connected = key save ayyindhi ✓ · Waiting on you = okka email-link tap leda SMS code matrame kavali · Not set = inka cheyyaledu · Test fail = key work avvatledhu, malli try cheyyi.", stepWaiting: "Nee okka tap kosam wait — email link leda SMS code", stepYouDo: "Ee step ni Divya chesthundhi — neeku emi cheyalsina pani ledu.", setupNeedEmail: "Kotha accounts kosam email kavali — Profile lo email set cheyyi.", setupOpen: "Browser lo open cheyyi", setupStop: "Stop task", setupTake: "Take control", setupContinue: "Continue", setupDone: "Setup ayyindhi ✓", setupRunning: "Setup nadusthundhi…", setupPaused: "Pause ayyindhi — nee okka tap kosam aagindhi.", setupFailed: "Setup fail ayyindhi.", setupAsk: "Setup cheyala? Divya anni setup chesthundhi — accounts, API keys, server — neeku emi cheyalsina pani undadhu.", setupAllow: "Setup cheyu", setupDoneMsg: "Setup aipoyindhi ✓ — chat ippudu ready", setupStepDone: "Ayyindhi ✓", setupStepRunning: "Jarugutondhi…", setupStepPaused: "Nee okka tap kosam aagindhi", setupStepFailed: "Fail ayyindhi — migilina steps tho continue chesthunna", setupPauseEmail: "Nee email lo vachina link ni okkasari tap cheyu, migilina anni nene chestha.", setupPauseSms: "Phone ki vachina SMS code ni ikkada ivvu, migilina anni nene chestha.", setupDidIt: "Nenu chesa ✓", setupPauseSignin: "Sign-in kavali — 'Browser lo open cheyyi' tho sign in cheyu, tarvatha 'Nenu chesa ✓' nokku.", setupPauseCaptcha: "Image challenge vachindhi — 'Take control' tho okkasari chusi continue cheyu.", setupStalled: "Setup aagipoyindhi — runner nunchi update ledu.", autoLogT: "Divya thane chesina setup — auto log", setupRetry: "Setup malli cheyu", openYT: "YouTube open cheyyi", setupYouEmail: "Nee email lo vachina verification link ni okkasari tap cheyu — migilina anni nene chestha.", setupYouSms: "Phone ki vachina SMS code ni okkasari ivvu — migilina anni nene chestha.", capSolving: "Captcha vachindhi — Divya ne solve chesthundhi, nee allow tho.", capNeedTap: "Image challenge aithe okka tap cheppu, nenu solve chestha.",
  },
  en: {
    skip: "Skip to content", numLabel: "WhatsApp number", codeLabel: "6-digit code",
    loginSub: "Enter your WhatsApp number. The code comes on WhatsApp.", loginSub2: "Your personal AI. Log in or create an account.", loginWays: "Ways to log in", tabLogin: "Log in", tabSignup: "Sign up", tabWa: "WhatsApp code",
    idLabel: "Email or phone number", idPh: "Email or phone number", pwLabel: "Password", newPwLabel: "Password (8+ characters)", nameLabel: "Your name", emailLabel: "Email", phoneLabel: "Phone (WhatsApp) — optional", showPw: "Show password",
    logIn: "Log in", forgot: "Forgot password?", createAcct: "Create account", suHint: "Your phone links only after you verify it with a WhatsApp code. New accounts start on the Free plan.",
    forgotT: "Reset password", forgotSub: "Enter your email or verified phone. The reset code goes to your verified WhatsApp.", sendResetCode: "Send reset code", backLogin: "Back to log in", setPw: "Set new password", rsSentTo: n => `Code sent on WhatsApp to ${n}.`,
    verifyPhoneT: "Verify phone", pvSentTo: n => `We sent a 6-digit code on WhatsApp to ${n}.`, later: "Later", needId: "Enter your email or phone.", needPw: "Enter your password.", need10: "Enter a 10-digit number.", triesLeft: n => ` (${n} tries left)`,
    netBlockedT: "Can't reach Divya's server.", netBlocked: "Your network (ISP) may be blocking *.workers.dev. Switch between mobile data and Wi-Fi, or turn on Private DNS (1.1.1.1 / dns.google).", offline: "You're offline. Check your connection and try again.", retry: "Try again",
    account: "Account", phoneOk: n => `Phone: ${n} ✓ verified`, phoneNone: "No phone linked. Link one to log in by phone and reset your password.", phonePend: n => `Phone ${n}: not verified yet.`, sendCode: "Send code", phoneLinked: "Phone linked ✓", delAcct: "Delete account", delWarn: "This deletes your account, login and app chat history. Confirm with your password.", delConfirm: "Confirm delete", deleted: "Account deleted.", getCode: "Send code", verify: "Log in", codeHint: "No code? Send \"login\" to Divya on WhatsApp.", changeNum: "Change number", codeSentTo: n => `Code sent on WhatsApp to +${n}.`, waitCode: "Code already sent. Check WhatsApp.",
     sProfile: "Profile", tHome: "Home", tVoice: "Voice", tChat: "Chat", tSetup: "Setup", tPlan: "Plan", tabsLabel: "Main tabs", openProfile: "Open profile",
    editsLeftT: "Free shorts left", notVerified: "not verified", quotaSub: (u, l) => `${u} of ${l} shorts used this week · resets Monday`, unlimited: "Unlimited", unlimitedSub: "Owner/friend — no limit",
        tooBig: "This file is over 24 MB. Attach a video under 24 MB.", attachVideoMsg: "Edit this video in chat", attachChatNote: "Will edit in chat",
    editsLine: (left, l) => l === null ? "Unlimited shorts (owner/friend)" : `${left} of ${l} free shorts left this week`,
    jobQueued: "Edit is queued", jobRunSub2: "This takes a few minutes. The download appears here when it's ready.", jobDoneSub2: "Download it (kept for 3 days).", jobFailSub2: "This one didn't count toward your free edits. Check the link/file and try again.",
    email: "Email", phone: "Phone", planL: "Plan", planFree: "Free", planPrem: "Premium (owner/friend)", waLogin: "WhatsApp login", f0: "5 free shorts a week",
    openMenu: "Open menu", closeMenu: "Close menu", menu: "Main menu", heyDivya: "Hey Divya — talk", quickActions: "Shortcuts",
    sHome: "Home", sChat: "Chat", sVoice: "Voice assistant", sConnect: "Connect accounts", sSetup: "Server & API setup", sPlan: "Subscription", sDownload: "Download app", sSettings: "Settings", logout: "Log out",
    gChat: "Chat", gVoice: "Voice", gConnect: "Connect", gSetup: "Server setup", gPlan: "Plan", gDownload: "Download", gSettings: "Settings",
    screen: n => `${n} screen`,
    hello: h => h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening", greetSub: "What shall we do today?", heySub: "Tap and speak: call, WhatsApp, open, songs, reminders",
    noJob: "No edit yet", noJobSub: "Tell me a topic in chat — Divya creates the video.",
    online: "Online", thinking: "Typing…", listening: "Listening…", releaseToSend: "Release to send", typeMsg: "Message…", bubblePh: "Chat with Divya…", holdMic: "Press and hold the mic, speak, then let go.", holdToTalk: "Press and hold to talk, or send message", attachImage: "Send image or video",
    emptyTitle: "Hi, I'm Divya", emptySub: "Chat, talk, or give me a task.", s1: "Open YouTube", s2: "What time is it?", s3: "What can you do?",
    length: "Length",
    jobRun: "Editing your video", jobRunSub: "This takes a few minutes. I'll send it here when ready.", jobDone: "Edit ready ✓", jobDoneSub: "Watch it in chat.", jobFail: "Edit failed", jobFailSub: "Try again.", started: "Video started! I'll send it right here when ready.",
    tapToTalk: "Tap to talk", vIdle: "Tap to talk", vWake: "Listening for \"Hey Divya\"…", vListen: "Listening… go ahead", vThink: "Thinking…", vSpeak: "Speaking…", vNoSR: "Always-listening isn't supported in this browser. Press and hold the orb to talk.",
    wakeSub: "Listens only while the app is open on screen", freeTitle: "Free:", freeList: "5 shorts a week (free), calls, WhatsApp messages, open apps/sites, songs, reminders, time, weather, short questions.", proTitle: "Pro:", proList: "unlimited shorts, multi-step agent tasks, long research, account automation.",
    voiceHonest: "Divya listens only while the app is open on screen (a web app can't listen in the background). It can't call or send WhatsApp silently: it opens the dialer or WhatsApp with everything filled in, and you tap Call or Send. Speech recognition runs through the browser's service (Google in Chrome).",
    callBtn: n => `Call ${n}`, waBtn: "Open WhatsApp", openBtn: n => `Open ${n}`, playBtn: "Listen on YouTube", openedTab: n => `Opened ${n} in a new tab`, openedApp: n => `Opened ${n}`, openYTApp: "Opened the YouTube app ✓", ytNoApp: "YouTube app isn't on this phone — opened in the browser instead.", ytOpening: "Opening the YouTube app…", waApp: "Opened the WhatsApp app ✓", waNoApp: "WhatsApp app isn't on this phone — opened in the browser instead.", waOpening: "Opening the WhatsApp app…", updBanner: v => `New version ${v} is out — refresh to get it.`, updRefresh: "Refresh", updCheck: "Check for app updates", updLatest: "App is on the latest version ✓", openBlocked: "Browser blocked it — tap the link below", openOff: "Auto-open is off — tap the link below", calBtn: "Add to Google Calendar", subBtn: "See plans", pickContact: "Pick from contacts", typeNumber: "Type number",
    noNumber: n => `I don't have ${n}'s number. Say "save ${n} 98xxxxxxxx", or pick from contacts.`, askNumber: n => `${n}'s phone number?`, saved: (n, x) => `Saved ${n} (+${x}). It stays on this phone only.`,
    remFire: t => `Reminder: ${t}`, notifTitle: "Divya reminder",
    connectNote: "Sign-in opens in your browser. Come back here when done.", connect: "Connect", connectedP: "Connected", soon: "Soon",
    setupIntro: "Divya sets itself up inside YOUR own accounts — Groq, OpenRouter, Gemini (free AI keys) + Cloudflare (your server). Divya does everything — accounts, API keys, server setup — with your one allow. You don't have to do anything.",
    googleRow: "Continue with Google", googleSub: "Uses your email for setup", continueGoogle: "Continue", orLoginPw: "Or log in with a password",
    consent: "I allow Divya to save my keys encrypted and use them only for my requests.", guideBtn: "🔊 Manual setup by voice",
    needConsent: "Please tick the permission box first.", allow: "Allow", cancel: "Cancel", save: "Save", next: "Next step", done: "Done", delData: "Delete my data", delDataConfirm: "Your account, chats and tokens will all be deleted. This can't be undone. Confirm?", delDataDone: "Your data has been deleted.", templateLabel: "Style template",
    stepNot: "Not set", stepOk: w => `Connected${w ? " · " + w : ""}`, stepFail: "Test failed", oneTap: "One-tap connect", openCreate: "Open & create key", pasteKey: "Paste key here", paste: "Paste", testSave: "Test & save", test: "Test", remove: "Remove", oauthSoon: "OAuth sign-in coming soon; paste a token for now.",
    foundKey: (n, l) => `Found a ${n} key (…${l}). Save it?`, keySaved: n => `${n} key saved and tested.`, keyBad: n => `That doesn't look like a ${n} key.`,
    guideStep: (n, d) => `${n} manual step. ${d} If you already have a key, paste it here — or use one-tap setup and Divya does everything.`, guideReturn: "Did you copy the key? Checking the clipboard.", guidePaste: "Paste the key in the box and tap Test and save.", guideDone: "All steps are done. Great!", guideNextQ: n => `Next: ${n}. Continue?`,
    serverTitle: "Your own server:", serverText: "Divya sets up the Cloudflare server too — with your one allow. You don't have to do anything.",
    d_openrouter: "Brain with free AI models (backup).", d_groq: "Fast brain + speech-to-text.", d_gemini: "Reads images and screenshots.", d_cloudflare: "For your own server (Worker).", d_github: "For the video machine (Actions).", d_huggingface: "For AI models and voices.",
    planNow: (p, u, l) => `Your plan: ${p === "premium" ? "Premium (owner/friend access)" : "Free"}. Shorts this week: ${l === null ? `${u} (no limit)` : `${u}/${l}`}.`,
    freePlan: "Free", f1: "Voice commands: call, WhatsApp, open apps, songs, reminders, time, weather", f2: "Chat & short questions", f3: "Voice-first mode for blind users", f4: "Use your own API keys",
    p1: "Unlimited video edits", p2: "Multi-step agent tasks, long research", p3: "Account automation (post/upload — with your OK)", priceSoon: "Price: soon", comingSoon: "Coming soon", noPayNote: "No payments yet. We'll tell you when Pro is ready.",
    installNow: "Install app", installed: "Divya is already installed as an app on this device ✓", canInstall: "One-tap install is available in this browser.", cantPrompt: "This browser doesn't show an install prompt — follow the steps below.", notApk: "This installs from your browser as an app (PWA). It's not a Play Store APK.",
    and1: "Open this page in Chrome.", and2: "Tap \"Install app\" above, or menu (⋮) → \"Install app\" / \"Add to Home screen\".", and3: "The Divya icon appears on your home screen.",
    ios1: "Open this page in Safari.", ios2: "Tap Share (□↑) → \"Add to Home Screen\".", ios3: "Tap \"Add\", then open Divya from your home screen.",
    pc1: "In Chrome/Edge, click the install icon (⊕ / monitor) in the address bar.", pc2: "Or menu → \"Install Divya\" / \"Apps → Install this site as an app\".",
    language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "When you speak, Divya answers aloud", voiceFirst: "Voice-first mode", voiceFirstSub: "Speaks every result and keeps listening after each answer (for blind users)", blindMode: "Blind Mode", blindModeSub: "Everything by voice — big buttons, high contrast, captcha guide, voice signup", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts",
    inviteTitle: "Invite friends", inviteSub: "When a friend joins, both get 1,000,000 tokens (10 shorts or 1× 10-minute video). Pool tokens never expire.", copy: "Copy", redeem: "Redeem", inviteStatus: (i, e) => `${i} invites · ${e} tokens earned`, tokSub: (w, p, v, d) => `${fmtTok(w)} tokens left this week · pool ${fmtTok(p)} · ${v} shorts · resets ${d}`, voiceSignup: "Sign up by voice", voiceIncluded: "Voice assistant included in every plan", capDone: "Captcha solved ✓", capNo: "OK, not solving.", capAskShot: "Send a screenshot of the captcha and I'll read the answer.", blindHello: "Blind Mode on. I'll say everything aloud. What shall we do?",
    netErr: "Network problem. Try again.", micDenied: "Allow microphone access in browser settings.", noRec: "Voice recording isn't supported in this browser.", loggedIn: n => `Logged in as ${n}`, orDone: "OpenRouter connected ✓", orFail: "OpenRouter didn't connect.",
    voicePick: "Voice (Divya's voice)", voiceLoading: "Loading voices… (first time ~90 MB download)", voiceReady: "Voices ready ✓ (Kokoro)", voiceLoadFail: "Voices failed to load — check your internet and try again. Using the phone voice for now.", voiceRetry: "Retry loading voices", voiceRetryNote: "Kokoro didn't load — only the phone's system voice can play right now, so every voice sounds the same.", voicePlayedSystem: l => `That was not Kokoro — it played with the phone's system voice (${l}). Once Kokoro loads, you'll hear the selected voice.`, voiceNoVoice: "Voice could not play — Kokoro did not load and the phone has no voice. Check your internet.", voiceSample: "Hi, I'm Divya. I'll speak in this voice.", vChild: "Child", vTeen: "Teenage", vAdult: "Age 30–60", vElder: "Aged 60+", vFemale: "Female", vMale: "Male", gsAsk: "Shall I set everything up? Divya does it all — accounts, API keys, server — you don't have to do anything.", gsDeclined: "OK, no setup. Chat still works — you can start setup anytime from the Setup screen.", gsStopped: "OK, stopping here. You can continue from the Setup screen.", gsVerifyAsk: "The verification mail is here — tap the link once, Divya does the rest.", sPost: "Post to YouTube", postIntro: "Post your edited video to YouTube. Add a title, description and tags — you can also schedule it.", postVideo: "Video (job id or link)", postJobPh: "Job id or video link", postTitle: "Title", postDesc: "Description", postTags: "Tags (comma-separated)", postTagsPh: "divya, ai, video", postPrivacy: "Privacy", postSchedule: "Schedule (optional)", postThumb: "Thumbnail (optional)", postBtn: "Post to YouTube", postDone: "Posted ✓", postViews: "Views", postLikes: "Likes", postComments: "Comments", postNeedVideo: "Give a video job id or link.", sHistory: "My videos", gHistory: "My videos", histIntro: "Edited videos — numbered video 1, video 2. To upload, say 'upload video 1' in chat.", histEmpty: "No videos yet. Attach a video in chat.", histWatch: "Watch / Download", histUpload: "Upload", histDone: "Ready", histFail: "Failed", histEditing: "Editing",
    setupOneTap: "Start one-tap setup (one allow)", setupConsent: "With one allow, Divya does everything — creating accounts, taking API keys, solving captchas, setting up the server. You don't have to do anything.", setupHowT: "How does setup work?", setupHowDivyaT: "Divya does:", setupHowDivya: "creating accounts, taking API keys, solving captchas, and setting up the Cloudflare server — all by Divya, with your one allow.", setupHowYouT: "Only once, from you:", setupHowAfterT: "After that:", setupHowAfter: "once setup is done, Divya tells you in chat — from then on Divya works with your accounts.", setupHowNote: "Divya does everything — with your allow. Apart from the email-link tap / SMS code, you don't have to do anything.", setupStepNote: "Each step below shows its state: Connected = key saved ✓ · Waiting on you = only one email-link tap or SMS code is needed · Not set = not done yet · Test failed = the key didn't work, try again.", stepWaiting: "Waiting for your one tap — email link or SMS code", stepYouDo: "Divya is doing this step — you don't have to do anything.", setupNeedEmail: "An email is needed for the new accounts — set it in Profile.", setupOpen: "Open in browser", setupStop: "Stop task", setupTake: "Take control", setupContinue: "Continue", setupDone: "Setup done ✓", setupRunning: "Setup running…", setupPaused: "Paused — waiting for your one tap.", setupFailed: "Setup failed.", setupAsk: "Shall I set everything up? Divya does it all — accounts, API keys, server — you don't have to do anything.", setupAllow: "Set it up", setupDoneMsg: "Setup is done ✓ — chat is ready now", setupStepDone: "Done ✓", setupStepRunning: "Running…", setupStepPaused: "Paused for your one tap", setupStepFailed: "Failed — continuing with the other steps", setupPauseEmail: "Tap the verification link in your email once — Divya does the rest.", setupPauseSms: "Enter the SMS code sent to your phone — Divya does the rest.", setupDidIt: "I did it ✓", setupPauseSignin: "A sign-in is needed — open it in the browser, sign in, then tap 'I did it ✓'.", setupPauseCaptcha: "An image challenge came up — use 'Take control' to do that one step, then continue.", setupStalled: "Setup stalled — no update from the runner.", autoLogT: "What Divya set up on its own — auto log", setupRetry: "Run setup again", openYT: "Open YouTube", setupYouEmail: "Tap the verification link in your email once — Divya does the rest.", setupYouSms: "Enter the SMS code sent to your phone once — Divya does the rest.", capSolving: "A captcha appeared — Divya is solving it with your allow.", capNeedTap: "If it's an image challenge, one tap from you and I'll solve it.",
  },
  hi: {
    skip: "सामग्री पर जाएँ", numLabel: "WhatsApp नंबर", codeLabel: "6 अंकों का कोड", loginSub: "अपना WhatsApp नंबर डालें। कोड WhatsApp पर आएगा।", loginSub2: "आपकी निजी AI। लॉग इन करें या नया अकाउंट बनाएँ।", loginWays: "लॉग इन करने के तरीके", tabLogin: "लॉग इन", tabSignup: "साइन अप", tabWa: "WhatsApp कोड", idLabel: "ईमेल या फ़ोन नंबर", idPh: "ईमेल या फ़ोन नंबर", pwLabel: "पासवर्ड", newPwLabel: "पासवर्ड (कम से कम 8)", nameLabel: "आपका नाम", emailLabel: "ईमेल", phoneLabel: "फ़ोन (WhatsApp) — वैकल्पिक", showPw: "पासवर्ड दिखाएँ", logIn: "लॉग इन", forgot: "पासवर्ड भूल गए?", createAcct: "अकाउंट बनाएँ", suHint: "फ़ोन WhatsApp कोड से वेरीफ़ाई होने के बाद ही लिंक होगा। नए अकाउंट Free प्लान पर शुरू होते हैं।",
    forgotT: "पासवर्ड रीसेट", forgotSub: "अपना ईमेल या वेरीफ़ाई किया हुआ फ़ोन डालें। रीसेट कोड आपके वेरीफ़ाई किए WhatsApp पर जाएगा।", sendResetCode: "रीसेट कोड भेजें", backLogin: "लॉग इन पर वापस", setPw: "नया पासवर्ड सेट करें", rsSentTo: n => `${n} पर WhatsApp में कोड भेजा।`,
    verifyPhoneT: "फ़ोन वेरीफ़ाई करें", pvSentTo: n => `${n} पर WhatsApp में 6 अंकों का कोड भेजा।`, later: "बाद में", needId: "ईमेल या फ़ोन डालें।", needPw: "पासवर्ड डालें।", need10: "10 अंकों का नंबर डालें।", triesLeft: n => ` (${n} मौके बचे)`,
    netBlockedT: "Divya के सर्वर से कनेक्ट नहीं हो रहा।", netBlocked: "आपका नेटवर्क (ISP) *.workers.dev को ब्लॉक कर रहा हो सकता है। मोबाइल डेटा ↔ Wi-Fi बदलकर देखें, या Private DNS (1.1.1.1 / dns.google) चालू करें।", offline: "इंटरनेट नहीं है। कनेक्शन देखकर फिर कोशिश करें।", retry: "फिर कोशिश करें",
    account: "अकाउंट", phoneOk: n => `फ़ोन: ${n} ✓ वेरीफ़ाई हो गया`, phoneNone: "कोई फ़ोन लिंक नहीं है। लिंक करने पर फ़ोन से लॉग इन + पासवर्ड रीसेट मिलेगा।", phonePend: n => `फ़ोन ${n}: अभी वेरीफ़ाई नहीं हुआ।`, sendCode: "कोड भेजें", phoneLinked: "फ़ोन लिंक हो गया ✓", delAcct: "अकाउंट डिलीट करें", delWarn: "इससे आपका अकाउंट, लॉग इन, ऐप चैट हिस्ट्री डिलीट हो जाएगी। पासवर्ड से कन्फ़र्म करें।", delConfirm: "डिलीट कन्फ़र्म करें", deleted: "अकाउंट डिलीट हो गया।", getCode: "कोड भेजें", verify: "लॉग इन", codeHint: "कोड नहीं आया? WhatsApp पर Divya को \"login\" भेजें।", changeNum: "नंबर बदलें", codeSentTo: n => `+${n} पर WhatsApp में कोड भेजा।`, waitCode: "कोड पहले ही भेजा गया है। WhatsApp देखें।",
     sProfile: "प्रोफ़ाइल", tHome: "होम", tVoice: "वॉइस", tChat: "चैट", tSetup: "सेटअप", tPlan: "प्लान", tabsLabel: "मुख्य टैब", openProfile: "प्रोफ़ाइल खोलें",
    editsLeftT: "फ्री शॉर्ट्स बचे", notVerified: "वेरीफ़ाई नहीं हुआ", quotaSub: (u, l) => `इस हफ़्ते ${u}/${l} शॉर्ट्स इस्तेमाल किए · सोमवार को रीसेट`, unlimited: "अनलिमिटेड", unlimitedSub: "ओनर/दोस्त — कोई लिमिट नहीं",
                    tooBig: "यह फ़ाइल 24 MB से बड़ी है। 24 MB से छोटी वीडियो अटैच करें।", attachVideoMsg: "Is video ko chat mein edit karo", attachChatNote: "Chat mein edit hoga",
    editsLine: (left, l) => l === null ? "अनलिमिटेड शॉर्ट्स (ओनर/दोस्त)" : `इस हफ़्ते ${left}/${l} फ्री शॉर्ट्स बचे`,
    jobQueued: "एडिट कतार में है", jobRunSub2: "थोड़ा समय लगेगा। तैयार होने पर डाउनलोड यहीं मिलेगा।", jobDoneSub2: "डाउनलोड करें (3 दिन तक रहेगा)।", jobFailSub2: "यह एडिट आपके फ्री काउंट में नहीं गिना गया। लिंक/फ़ाइल देखकर फिर कोशिश करें।",
    email: "ईमेल", phone: "फ़ोन", planL: "प्लान", planFree: "फ्री", planPrem: "प्रीमियम (ओनर/दोस्त)", waLogin: "WhatsApp लॉग इन", f0: "हफ़्ते में 5 शॉर्ट्स (फ्री)",
    openMenu: "मेनू खोलें", closeMenu: "मेनू बंद करें", menu: "मुख्य मेनू", heyDivya: "हे Divya — बोलिए", quickActions: "शॉर्टकट", sHome: "होम", sChat: "चैट", sVoice: "वॉइस असिस्टेंट", sConnect: "अकाउंट कनेक्ट", sSetup: "सर्वर और API सेटअप", sPlan: "सब्सक्रिप्शन", sDownload: "ऐप डाउनलोड", sSettings: "सेटिंग्स", logout: "लॉग आउट", gChat: "चैट", gVoice: "वॉइस", gConnect: "कनेक्ट", gSetup: "सर्वर सेटअप", gPlan: "प्लान", gDownload: "डाउनलोड", gSettings: "सेटिंग्स",
    screen: n => `${n} स्क्रीन`,
    hello: h => h < 12 ? "नमस्ते, good morning" : h < 17 ? "नमस्ते, good afternoon" : "नमस्ते, good evening", greetSub: "आज क्या करें?", heySub: "टैप करके बोलें: कॉल, WhatsApp, खोलें, गाने, रिमाइंडर",
    noJob: "कोई एडिट नहीं है", noJobSub: "चैट में टॉपिक बताओ — दिव्या वीडियो बना देगी।", online: "ऑनलाइन", thinking: "टाइप कर रही है…", listening: "सुन रही हूँ…", releaseToSend: "छोड़ने पर भेजा जाएगा", typeMsg: "मैसेज…", bubblePh: "Divya se baat karo…", holdMic: "माइक दबाकर रखें, बोलें, फिर छोड़ें।", holdToTalk: "दबाकर रखें और बोलें, या मैसेज भेजें", attachImage: "इमेज / वीडियो भेजें", emptyTitle: "नमस्ते, मैं Divya हूँ", emptySub: "चैट करें, बोलें, या काम बताएँ।", s1: "YouTube खोलें", s2: "अभी समय क्या है?", s3: "तुम क्या-क्या कर सकती हो?",
    length: "लंबाई", jobRun: "एडिट हो रहा है", jobRunSub: "थोड़ा समय लगेगा। तैयार होने पर यहीं भेजूँगी।", jobDone: "एडिट तैयार ✓", jobDoneSub: "Chat में देखें।", jobFail: "एडिट फ़ेल हो गया", jobFailSub: "फिर कोशिश करें।", started: "वीडियो शुरू कर दिया! तैयार होने पर यहीं भेजूँगी।", tapToTalk: "टैप करके बोलें", vIdle: "टैप करके बोलें", vWake: "\"Hey Divya\" के लिए सुन रही हूँ…", vListen: "सुन रही हूँ… बोलिए", vThink: "सोच रही हूँ…", vSpeak: "बोल रही हूँ…", vNoSR: "इस ब्राउज़र में हमेशा-सुनना नहीं है। बोलने के लिए ऑर्ब को दबाकर रखें।", wakeSub: "सिर्फ़ जब ऐप स्क्रीन पर खुला हो, तब सुनती है",
    freeTitle: "फ्री:", freeList: "हफ़्ते में 5 शॉर्ट्स (फ्री), कॉल, WhatsApp मैसेज, ऐप्स/साइट खोलना, गाने, रिमाइंडर, समय, मौसम, छोटे सवाल।", proTitle: "प्रो:", proList: "अनलिमिटेड शॉर्ट्स, मल्टी-स्टेप एजेंट काम, लंबी रिसर्च, अकाउंट ऑटोमेशन।",
    voiceHonest: "Divya सिर्फ़ जब ऐप खुला हो और स्क्रीन पर हो, तब सुनती है (वेब ऐप बैकग्राउंड में नहीं सुनता)। कॉल/WhatsApp चुपचाप नहीं भेज सकती: डायलर या WhatsApp सब कुछ भरकर खोलती है, आप Call/Send दबाते हैं। वॉइस पहचान ब्राउज़र की सर्विस (Chrome में Google) से होती है।",
    callBtn: n => `कॉल करें ${n}`, waBtn: "WhatsApp खोलें", openBtn: n => `${n} खोलें`, playBtn: "YouTube पर सुनें", openedTab: n => `${n} naye tab mein khola`, openedApp: n => `${n} khola`, openYTApp: "YouTube ऐप खुल गया ✓", ytNoApp: "YouTube ऐप फ़ोन में नहीं है — ब्राउज़र में खोला।", ytOpening: "YouTube ऐप खोल रही हूँ…", waApp: "WhatsApp ऐप खुल गया ✓", waNoApp: "WhatsApp ऐप फ़ोन में नहीं है — ब्राउज़र में खोला।", waOpening: "WhatsApp ऐप खोल रही हूँ…", updBanner: v => `नया वर्शन ${v} आ गया — रिफ्रेश करें।`, updRefresh: "रिफ्रेश करें", updCheck: "ऐप अपडेट चेक करें", updLatest: "ऐप लेटेस्ट वर्शन पर है ✓", openBlocked: "Browser ne roka — neeche link dabao", openOff: "Auto-open band hai — neeche link dabao", calBtn: "Google Calendar में जोड़ें", subBtn: "प्लान देखें", pickContact: "कॉन्टैक्ट से चुनें", typeNumber: "नंबर टाइप करें", noNumber: n => `${n} का नंबर मेरे पास नहीं है। "${n} सेव करें 98xxxxxxxx" कहें, या कॉन्टैक्ट से चुनें।`, askNumber: n => `${n} का फ़ोन नंबर?`, saved: (n, x) => `${n} का नंबर सेव कर लिया (+${x})। यह सिर्फ़ इसी फ़ोन में रहेगा।`, remFire: t => `रिमाइंडर: ${t}`, notifTitle: "Divya रिमाइंडर",
    connectNote: "लॉग इन पेज ब्राउज़र में खुलेगा। कनेक्ट होने के बाद यहाँ वापस आएँ।", connect: "कनेक्ट", connectedP: "कनेक्टेड", soon: "जल्द आ रहा है",
    setupIntro: "Divya आपके अपने accounts में setup हो जाती है — Groq, OpenRouter, Gemini (free AI keys) + Cloudflare (आपका server)। Divya सब कुछ करती है — accounts, API keys, server setup — आपके एक allow से। आपको कुछ नहीं करना है।",
    googleRow: "Continue with Google", googleSub: "आपका ईमेल सेटअप के लिए इस्तेमाल होगा", continueGoogle: "जारी रखें", orLoginPw: "या पासवर्ड से लॉग इन करें",
    consent: "मैं Divya को अपनी keys एन्क्रिप्ट करके सेव करने और सिर्फ़ मेरी रिक्वेस्ट के लिए इस्तेमाल करने की परमिशन देता/देती हूँ।",
    guideBtn: "🔊 वॉइस से मैनुअल सेटअप", needConsent: "पहले परमिशन बॉक्स पर टिक करें।", allow: "अलाउ करें", cancel: "कैंसिल", save: "सेव करें", next: "अगला स्टेप", done: "हो गया", delData: "मेरा डेटा डिलीट करें", delDataConfirm: "आपका अकाउंट, चैट, टोकन — सब डिलीट हो जाएगा। यह वापस नहीं होगा। कन्फ़र्म करें?", delDataDone: "आपका डेटा डिलीट कर दिया गया।", templateLabel: "स्टाइल टेम्पलेट",
    stepNot: "अभी सेट नहीं है", stepOk: w => `कनेक्टेड${w ? " · " + w : ""}`, stepFail: "टेस्ट फ़ेल", oneTap: "वन-टैप कनेक्ट", openCreate: "खोलें और key बनाएँ", pasteKey: "Key यहाँ पेस्ट करें", paste: "पेस्ट करें", testSave: "टेस्ट और सेव करें", test: "टेस्ट", remove: "हटाएँ", oauthSoon: "OAuth लॉग इन जल्द आ रहा है; अभी टोकन पेस्ट करें।",
    foundKey: (n, l) => `${n} key मिली (…${l})। सेव करें?`, keySaved: n => `${n} key सेव हो गई, टेस्ट पास।`, keyBad: n => `यह ${n} key जैसी नहीं लगती।`,
    guideStep: (n, d) => `${n} मैनुअल step। ${d} अगर आपके पास key है तो यहाँ paste करें — या वन-टैप सेटअप से Divya सब कर देगी।`, guideReturn: "Key कॉपी कर ली? क्लिपबोर्ड देख रही हूँ।", guidePaste: "Key बॉक्स में पेस्ट करें और Test & save दबाएँ।", guideDone: "सारे स्टेप हो गए। बहुत बढ़िया!", guideNextQ: n => `अगला: ${n}। जारी रखूँ?`,
    serverTitle: "आपका अपना सर्वर:", serverText: "Cloudflare server भी Divya ही setup करती है — आपके एक allow से। आपको कुछ नहीं करना है।",
    d_openrouter: "फ्री AI मॉडल के साथ ब्रेन (बैकअप)।", d_groq: "फ़ास्ट ब्रेन + वॉइस-टू-टेक्स्ट।", d_gemini: "इमेज/स्क्रीनशॉट पढ़ने के लिए।", d_cloudflare: "आपके अपने सर्वर (Worker) के लिए।", d_github: "वीडियो मशीन (Actions) के लिए।", d_huggingface: "AI मॉडल/वॉइस के लिए।",
    planNow: (p, u, l) => `आपका प्लान: ${p === "premium" ? "प्रीमियम (ओनर/दोस्त एक्सेस)" : "फ्री"}। इस हफ़्ते शॉर्ट्स: ${l === null ? `${u} (कोई लिमिट नहीं)` : `${u}/${l}`}।`,
    freePlan: "फ्री", f1: "वॉइस कमांड: कॉल, WhatsApp, ऐप खोलना, गाने, रिमाइंडर, समय, मौसम", f2: "चैट और छोटे सवाल", f3: "ब्लाइंड यूज़र्स के लिए वॉइस-फ़र्स्ट मोड", f4: "अपनी API keys इस्तेमाल कर सकते हैं", p1: "अनलिमिटेड वीडियो एडिट", p2: "मल्टी-स्टेप एजेंट काम, लंबी रिसर्च", p3: "अकाउंट ऑटोमेशन (पोस्ट/अपलोड — आपकी OK के साथ)", priceSoon: "कीमत: जल्द आ रही है", comingSoon: "जल्द आ रहा है", noPayNote: "अभी पेमेंट नहीं है। Pro तैयार होने पर बताएँगे।",
    installNow: "ऐप इंस्टॉल करें", installed: "Divya इस डिवाइस में ऐप की तरह इंस्टॉल हो चुकी है ✓", canInstall: "इस ब्राउज़र में वन-टैप इंस्टॉल है।", cantPrompt: "यह ब्राउज़र ऑटो इंस्टॉल नहीं दिखाता — नीचे दिए स्टेप फॉलो करें।", notApk: "यह ब्राउज़र से ऐप की तरह इंस्टॉल होती है (PWA)। Play Store APK नहीं है।",
    and1: "Chrome में यह पेज खोलें।", and2: "ऊपर \"ऐप इंस्टॉल करें\" दबाएँ, या मेनू (⋮) → \"Install app\" / \"Add to Home screen\"।", and3: "होम स्क्रीन पर Divya आइकन आ जाएगा।",
    ios1: "Safari में यह पेज खोलें।", ios2: "Share (□↑) दबाएँ → \"Add to Home Screen\"।", ios3: "\"Add\" दबाएँ। होम स्क्रीन से खोलें।",
    pc1: "Chrome/Edge एड्रेस बार में इंस्टॉल आइकन (⊕ / मॉनिटर) दबाएँ।", pc2: "या मेनू → \"Install Divya\" / \"Apps → Install this site as an app\"।",
    language: "भाषा", voiceReplies: "वॉइस जवाब", voiceRepliesSub: "माइक में पूछने पर Divya ज़ोर से जवाब देती है", voiceFirst: "वॉइस-फ़र्स्ट मोड", voiceFirstSub: "हर रिज़ल्ट ज़ोर से बोलती है, जवाब के बाद फिर सुनती है (ब्लाइंड यूज़र्स के लिए)", blindMode: "ब्लाइंड मोड", blindModeSub: "सब कुछ वॉइस से — बड़े बटन, हाई कॉन्ट्रास्ट, कैप्चा गाइड, वॉइस साइनअप", theme: "थीम", auto: "ऑटो", light: "लाइट", dark: "डार्क", connected: "कनेक्टेड अकाउंट",
    inviteTitle: "दोस्तों को इन्वाइट करें", inviteSub: "एक दोस्त के जॉइन करने पर दोनों को 10 लाख टोकन मिलते हैं (10 शॉर्ट्स या 1× 10 मिनट का वीडियो)। पूल टोकन कभी एक्सपायर नहीं होते।", copy: "कॉपी करें", redeem: "रिडीम करें", inviteStatus: (i, e) => `${i} इन्वाइट · ${e} टोकन मिले`, tokSub: (w, p, v, d) => `इस हफ़्ते ${fmtTok(w)} टोकन बचे · पूल ${fmtTok(p)} · ${v} शॉर्ट्स · रीसेट ${d}`, voiceSignup: "वॉइस से साइन अप करें", voiceIncluded: "वॉइस असिस्टेंट हर प्लान में शामिल है", capDone: "कैप्चा सॉल्व हो गया ✓", capNo: "ठीक है, सॉल्व नहीं किया।", capAskShot: "कैप्चा का स्क्रीनशॉट भेजें, मैं पढ़कर जवाब बताऊँगी।", blindHello: "ब्लाइंड मोड ऑन। सब कुछ वॉइस से बताऊँगी। क्या करना है?",
    netErr: "नेटवर्क प्रॉब्लम। फिर कोशिश करें।", micDenied: "माइक परमिशन दें (ब्राउज़र सेटिंग्स में)।", noRec: "इस ब्राउज़र में वॉइस रिकॉर्ड नहीं होती।", loggedIn: n => `${n} से लॉग इन`, orDone: "OpenRouter कनेक्ट हो गया ✓", orFail: "OpenRouter कनेक्ट नहीं हुआ।",
    voicePick: "वॉइस (Divya की आवाज़)", voiceLoading: "Voices load ho rahi hain… (pehli baar ~90 MB download)", voiceReady: "Voices ready ✓ (Kokoro)", voiceLoadFail: "Voices load nahi hui — internet check karke phir try karo. Abhi phone voice se bol rahi hoon.", voiceRetry: "आवाज़ें फिर से लोड करें", voiceRetryNote: "Kokoro लोड नहीं हुआ — अभी सिर्फ़ फ़ोन की सिस्टम वॉइस बजेगी, इसलिए सभी आवाज़ें एक जैसी सुनाई देती हैं।", voicePlayedSystem: l => `Ye Kokoro nahi tha — phone ki system voice (${l}) se baja. Kokoro load hone par selected voice sunai degi.`, voiceNoVoice: "Voice play nahi hui — Kokoro load nahi hua, phone me voice bhi nahi hai. Internet check karo.", voiceSample: "नमस्ते, मैं Divya हूँ। मैं इसी आवाज़ में बोलूँगी।", vChild: "बच्चे", vTeen: "टीनएज", vAdult: "30–60", vElder: "60+ बुज़ुर्ग", vFemale: "महिला", vMale: "पुरुष", gsAsk: "क्या मैं सब कुछ setup करूँ? Divya सब करती है — accounts, API keys, server — आपको कुछ नहीं करना है।", gsDeclined: "ठीक है, सेटअप नहीं किया। चैट चलती रहेगी — Setup स्क्रीन से कभी भी शुरू कर सकते हैं।", gsStopped: "ठीक है, यहीं रुक रही हूँ। Setup स्क्रीन से जारी रख सकते हैं।", gsVerifyAsk: "वेरिफ़िकेशन मेल आ गया है — link को एक बार tap करें, बाकी सब Divya कर देगी।", sPost: "YouTube पोस्ट", postIntro: "एडिट किया वीडियो YouTube पर पोस्ट करें। टाइटल, डिस्क्रिप्शन और टैग दें — शेड्यूल भी कर सकते हैं।", postVideo: "वीडियो (job id या लिंक)", postJobPh: "Job id या वीडियो लिंक", postTitle: "टाइटल", postDesc: "डिस्क्रिप्शन", postTags: "टैग (कॉमा से अलग करें)", postTagsPh: "divya, ai, video", postPrivacy: "प्राइवेसी", postSchedule: "शेड्यूल (वैकल्पिक)", postThumb: "थंबनेल (वैकल्पिक)", postBtn: "YouTube पर पोस्ट करें", postDone: "पोस्ट हो गया ✓", postViews: "व्यूज़", postLikes: "लाइक्स", postComments: "कमेंट्स", postNeedVideo: "वीडियो job id या लिंक दें।", sHistory: "Mere videos", gHistory: "Mere videos", histIntro: "Edit kiye videos — video 1, video 2 number se. Upload ke liye chat me 'upload video 1' kaho.", histEmpty: "Abhi koi video nahi hai. Chat me video attach karo.", histWatch: "Dekho / Download", histUpload: "Upload karo", histDone: "Ready", histFail: "Fail ho gaya", histEditing: "Edit ho raha hai",
    setupOneTap: "वन-टैप सेटअप शुरू करें (एक allow)", setupConsent: "एक allow से Divya सब कुछ करती है — accounts बनाना, API keys लेना, captchas solve करना, server setup — सब Divya करती है। आपको कुछ नहीं करना है।", setupHowT: "सेटअप कैसे काम करता है?", setupHowDivyaT: "Divya करती है:", setupHowDivya: "accounts बनाना, API keys लेना, captchas solve करना, और Cloudflare server setup करना — सब Divya करती है, आपके एक allow से।", setupHowYouT: "आपसे सिर्फ़ एक बार:", setupHowAfterT: "उसके बाद:", setupHowAfter: "सेटअप होने पर Divya chat में बता देगी — उसके बाद Divya आपके accounts से काम करेगी।", setupHowNote: "Divya सब कुछ करती है — आपके allow से। Email link tap / SMS code के अलावा, आपको कुछ नहीं करना है।", setupStepNote: "नीचे हर step की state दिखती है: Connected = key save हो गई ✓ · Waiting on you = सिर्फ़ एक email-link tap या SMS code चाहिए · Not set = अभी नहीं हुआ · Test failed = key काम नहीं कर रही, फिर कोशिश करें।", stepWaiting: "आपके एक tap का इंतज़ार — email link या SMS code", stepYouDo: "यह step Divya कर रही है — आपको कुछ नहीं करना है।", setupNeedEmail: "नए अकाउंट के लिए ईमेल चाहिए — प्रोफ़ाइल में ईमेल सेट करो।", setupOpen: "ब्राउज़र में खोलो", setupStop: "Stop task", setupTake: "Take control", setupContinue: "Continue", setupDone: "सेटअप हो गया ✓", setupRunning: "सेटअप चल रहा है…", setupPaused: "रुका हुआ है — आपके एक tap का इंतज़ार है।", setupFailed: "सेटअप फ़ेल हो गया।", setupAsk: "क्या मैं सब कुछ setup करूँ? Divya सब करती है — accounts, API keys, server — आपको कुछ नहीं करना है।", setupAllow: "सेटअप करो", setupDoneMsg: "सेटअप हो गया ✓ — चैट अब तैयार है", setupStepDone: "हो गया ✓", setupStepRunning: "चल रहा है…", setupStepPaused: "आपके एक tap के लिए रुका है", setupStepFailed: "फ़ेल हो गया — बाकी steps से जारी है", setupPauseEmail: "अपने email में आए link को एक बार tap करें — बाकी सब Divya कर देगी।", setupPauseSms: "फ़ोन पर आए SMS code को डालें — बाकी सब Divya कर देगी।", setupDidIt: "मैंने कर दिया ✓", setupPauseSignin: "साइन-इन चाहिए — ब्राउज़र में खोलकर साइन-इन करें, फिर 'मैंने कर दिया ✓' दबाएँ।", setupPauseCaptcha: "इमेज चैलेंज आया है — 'Take control' से वह एक स्टेप करें, फिर जारी रखें।", setupStalled: "सेटअप रुक गया है — रनर से अपडेट नहीं आया।", autoLogT: "Divya ने खुद क्या setup किया — auto log", setupRetry: "सेटअप फिर से चलाएँ", openYT: "YouTube खोलें", setupYouEmail: "अपने email में आए verification link को एक बार tap करें — बाकी सब Divya कर देगी।", setupYouSms: "फ़ोन पर आए SMS code को एक बार डालें — बाकी सब Divya कर देगी।", capSolving: "Captcha आ गया है — Divya आपके allow से खुद solve कर रही है।", capNeedTap: "अगर image challenge है तो एक tap करें, मैं solve कर दूँगी।",
  },
  "hi-Latn": {
    skip: "Content par jao", numLabel: "WhatsApp number", codeLabel: "6 digit ka code", loginSub: "Apna WhatsApp number dalo. Code WhatsApp par aayega.", loginSub2: "Aapki personal AI. Log in karo ya naya account banao.", loginWays: "Log in karne ke tareeke", tabLogin: "Log in", tabSignup: "Sign up", tabWa: "WhatsApp code", idLabel: "Email ya phone number", idPh: "Email ya phone number", pwLabel: "Password", newPwLabel: "Password (kam se kam 8)", nameLabel: "Aapka naam", emailLabel: "Email", phoneLabel: "Phone (WhatsApp) — optional", showPw: "Password dikhao", logIn: "Log in", forgot: "Password bhool gaye?", createAcct: "Account banao", suHint: "Phone WhatsApp code se verify hone ke baad hi link hoga. Naye accounts Free plan par shuru hote hain.",
    forgotT: "Password reset", forgotSub: "Apna email ya verified phone dalo. Reset code aapke verified WhatsApp par jayega.", sendResetCode: "Reset code bhejo", backLogin: "Log in par wapas", setPw: "Naya password set karo", rsSentTo: n => `${n} par WhatsApp me code bheja.`,
    verifyPhoneT: "Phone verify karo", pvSentTo: n => `${n} par WhatsApp me 6 digit ka code bheja.`, later: "Baad me", needId: "Email ya phone dalo.", needPw: "Password dalo.", need10: "10 digit ka number dalo.", triesLeft: n => ` (${n} mauke bache)`,
    netBlockedT: "Divya ke server se connect nahi ho raha.", netBlocked: "Aapka network (ISP) *.workers.dev ko block kar raha ho sakta hai. Mobile data ↔ Wi-Fi badal kar dekho, ya Private DNS (1.1.1.1 / dns.google) on karo.", offline: "Internet nahi hai. Connection dekh kar phir try karo.", retry: "Phir try karo",
    account: "Account", phoneOk: n => `Phone: ${n} ✓ verify ho gaya`, phoneNone: "Koi phone link nahi hai. Link karne par phone se log in + password reset milega.", phonePend: n => `Phone ${n}: abhi verify nahi hua.`, sendCode: "Code bhejo", phoneLinked: "Phone link ho gaya ✓", delAcct: "Account delete karo", delWarn: "Isse aapka account, log in, app chat history delete ho jayegi. Password se confirm karo.", delConfirm: "Delete confirm karo", deleted: "Account delete ho gaya.", getCode: "Code bhejo", verify: "Log in", codeHint: "Code nahi aaya? WhatsApp par Divya ko \"login\" bhejo.", changeNum: "Number badlo", codeSentTo: n => `+${n} par WhatsApp me code bheja.`, waitCode: "Code pehle hi bheja gaya hai. WhatsApp dekho.",
     sProfile: "Profile", tHome: "Home", tVoice: "Voice", tChat: "Chat", tSetup: "Setup", tPlan: "Plan", tabsLabel: "Main tabs", openProfile: "Profile kholo",
    editsLeftT: "Free shorts bache", notVerified: "verify nahi hua", quotaSub: (u, l) => `Is hafte ${u}/${l} shorts use kiye · Monday ko reset`, unlimited: "Unlimited", unlimitedSub: "Owner/friend — koi limit nahi",
                    tooBig: "Ye file 24 MB se badi hai. 24 MB se chhoti video attach karo.", attachVideoMsg: "Is video ko chat me edit karo", attachChatNote: "Chat me edit hoga",
    editsLine: (left, l) => l === null ? "Unlimited shorts (owner/friend)" : `Is hafte ${left}/${l} free shorts bache`,
    jobQueued: "Edit queue me hai", jobRunSub2: "Thoda time lagega. Ready hone par download yahin milega.", jobDoneSub2: "Download karo (3 din tak rahega).", jobFailSub2: "Ye edit aapke free count me nahi gina gaya. Link/file dekh kar phir try karo.",
    email: "Email", phone: "Phone", planL: "Plan", planFree: "Free", planPrem: "Premium (owner/friend)", waLogin: "WhatsApp log in", f0: "Hafte me 5 shorts (free)",
    openMenu: "Menu kholo", closeMenu: "Menu band karo", menu: "Main menu", heyDivya: "Hey Divya — bolo", quickActions: "Shortcuts", sHome: "Home", sChat: "Chat", sVoice: "Voice assistant", sConnect: "Accounts connect", sSetup: "Server & API setup", sPlan: "Subscription", sDownload: "App download", sSettings: "Settings", logout: "Log out", gChat: "Chat", gVoice: "Voice", gConnect: "Connect", gSetup: "Server setup", gPlan: "Plan", gDownload: "Download", gSettings: "Settings",
    screen: n => `${n} screen`,
    hello: h => h < 12 ? "Namaste, good morning" : h < 17 ? "Namaste, good afternoon" : "Namaste, good evening", greetSub: "Aaj kya karein?", heySub: "Tap karke bolo: call, WhatsApp, open, gaane, reminders",
    noJob: "Koi edit nahi hai", noJobSub: "Chat me topic batao — Divya video bana degi.", online: "Online", thinking: "Typing…", listening: "Sun rahi hoon…", releaseToSend: "Chhodne par bheja jayega", typeMsg: "Message…", bubblePh: "Divya se baat karo…", holdMic: "Mic dabakar rakho, bolo, phir chhodo.", holdToTalk: "Dabakar rakho aur bolo, ya message bhejo", attachImage: "Image / video bhejo", emptyTitle: "Namaste, main Divya hoon", emptySub: "Chat karo, bolo, ya kaam batao.", s1: "YouTube kholo", s2: "Abhi time kya hai?", s3: "Tum kya-kya kar sakti ho?",
    length: "Length", jobRun: "Edit ho raha hai", jobRunSub: "Thoda time lagega. Ready hone par yahin bhejungi.", jobDone: "Edit ready ✓", jobDoneSub: "Chat me dekho.", jobFail: "Edit fail ho gaya", jobFailSub: "Phir try karo.", started: "Video shuru kar diya! Ready hone par yahin bhejungi.", tapToTalk: "Tap karke bolo", vIdle: "Tap karke bolo", vWake: "\"Hey Divya\" ke liye sun rahi hoon…", vListen: "Sun rahi hoon… bolo", vThink: "Soch rahi hoon…", vSpeak: "Bol rahi hoon…", vNoSR: "Is browser me always-listening nahi hai. Bolne ke liye orb ko dabakar rakho.", wakeSub: "Sirf jab app screen par khula ho, tab sunti hai",
    freeTitle: "Free:", freeList: "Hafte me 5 shorts (free), calls, WhatsApp message, apps/sites open, gaane, reminders, time, weather, chhote sawaal.", proTitle: "Pro:", proList: "unlimited shorts, multi-step agent kaam, long research, account automation.",
    voiceHonest: "Divya sirf jab app khula ho aur screen par ho, tab sunti hai (web app background me nahi sunta). Call/WhatsApp chupchaap nahi bhej sakti: dialer ya WhatsApp sab kuch bharkar kholti hai, aap Call/Send dabate hain. Voice pehchan browser ki service (Chrome me Google) se hoti hai.",
    callBtn: n => `Call karo ${n}`, waBtn: "WhatsApp kholo", openBtn: n => `${n} kholo`, playBtn: "YouTube par suno", openedTab: n => `${n} naye tab mein khola`, openedApp: n => `${n} khola`, openYTApp: "YouTube app khul gaya ✓", ytNoApp: "YouTube app phone mein nahi hai — browser mein khola.", ytOpening: "YouTube app khol rahi hoon…", waApp: "WhatsApp app khul gaya ✓", waNoApp: "WhatsApp app phone mein nahi hai — browser mein khola.", waOpening: "WhatsApp app khol rahi hoon…", updBanner: v => `Naya version ${v} aa gaya — refresh karo.`, updRefresh: "Refresh karo", updCheck: "App update check karo", updLatest: "App latest version par hai ✓", openBlocked: "Browser ne roka — neeche link dabao", openOff: "Auto-open band hai — neeche link dabao", calBtn: "Google Calendar me jodo", subBtn: "Plans dekho", pickContact: "Contacts se chuno", typeNumber: "Number type karo", noNumber: n => `${n} ka number mere paas nahi hai. "${n} save karo 98xxxxxxxx" kaho, ya contacts se chuno.`, askNumber: n => `${n} ka phone number?`, saved: (n, x) => `${n} ka number save kar liya (+${x}). Ye sirf isi phone me rahega.`, remFire: t => `Reminder: ${t}`, notifTitle: "Divya reminder",
    connectNote: "Log in page browser me khulega. Connect hone ke baad yahan wapas aao.", connect: "Connect", connectedP: "Connected", soon: "Jald aa raha hai",
    setupIntro: "Divya aapke apne accounts me setup ho jati hai — Groq, OpenRouter, Gemini (free AI keys) + Cloudflare (aapka server). Divya sab kuch karti hai — accounts, API keys, server setup — aapke ek allow se. Aapko kuch nahi karna hai.",
    googleRow: "Continue with Google", googleSub: "Aapka email setup ke liye use hoga", continueGoogle: "Continue", orLoginPw: "Ya password se log in karo",
    consent: "Main Divya ko apni keys encrypt karke save karne aur sirf meri requests ke liye use karne ki permission deta/deti hoon.",
    guideBtn: "🔊 Voice se manual setup", needConsent: "Pehle permission box par tick karo.", allow: "Allow", cancel: "Cancel", save: "Save", next: "Next step", done: "Ho gaya", delData: "Mera data delete karo", delDataConfirm: "Aapka account, chats, tokens — sab delete ho jayega. Ye wapas nahi hoga. Confirm karo?", delDataDone: "Aapka data delete kar diya gaya.", templateLabel: "Style template",
    stepNot: "Abhi set nahi hai", stepOk: w => `Connected${w ? " · " + w : ""}`, stepFail: "Test fail", oneTap: "One-tap connect", openCreate: "Kholo aur key banao", pasteKey: "Key yahan paste karo", paste: "Paste", testSave: "Test & save", test: "Test", remove: "Remove", oauthSoon: "OAuth log in jald aa raha hai; abhi token paste karo.",
    foundKey: (n, l) => `${n} key mili (…${l}). Save karein?`, keySaved: n => `${n} key save ho gayi, test pass.`, keyBad: n => `Ye ${n} key jaisi nahi lagti.`,
    guideStep: (n, d) => `${n} manual step. ${d} Agar aapke paas key hai to yahan paste karo — ya one-tap setup se Divya sab kar degi.`, guideReturn: "Key copy kar li? Clipboard dekh rahi hoon.", guidePaste: "Key box me paste karo aur Test & save dabao.", guideDone: "Saare steps ho gaye. Bahut badhiya!", guideNextQ: n => `Agla: ${n}. Jaari rakhoon?`,
    serverTitle: "Aapka apna server:", serverText: "Cloudflare server bhi Divya hi setup karti hai — aapke ek allow se. Aapko kuch nahi karna hai.",
    d_openrouter: "Free AI models ke saath brain (backup).", d_groq: "Fast brain + voice-to-text.", d_gemini: "Images/screenshots padhne ke liye.", d_cloudflare: "Aapke apne server (Worker) ke liye.", d_github: "Video machine (Actions) ke liye.", d_huggingface: "AI models/voices ke liye.",
    planNow: (p, u, l) => `Aapka plan: ${p === "premium" ? "Premium (owner/friend access)" : "Free"}। Is hafte shorts: ${l === null ? `${u} (koi limit nahi)` : `${u}/${l}`}।`,
    freePlan: "Free", f1: "Voice commands: call, WhatsApp, open apps, gaane, reminders, time, weather", f2: "Chat & chhote sawaal", f3: "Blind users ke liye voice-first mode", f4: "Apni API keys use kar sakte hain", p1: "Unlimited video edits", p2: "Multi-step agent kaam, long research", p3: "Account automation (post/upload — aapki OK ke saath)", priceSoon: "Price: jald aa raha hai", comingSoon: "Jald aa raha hai", noPayNote: "Abhi payments nahi hain. Pro ready hone par batayenge.",
    installNow: "App install karo", installed: "Divya is device me app ki tarah install ho chuki hai ✓", canInstall: "Is browser me one-tap install hai.", cantPrompt: "Ye browser auto install nahi dikhata — neeche diye steps follow karo.", notApk: "Ye browser se app ki tarah install hoti hai (PWA). Play Store APK nahi hai.",
    and1: "Chrome me ye page kholo.", and2: "Upar \"App install karo\" dabao, ya menu (⋮) → \"Install app\" / \"Add to Home screen\"।", and3: "Home screen par Divya icon aa jayega.",
    ios1: "Safari me ye page kholo.", ios2: "Share (□↑) dabao → \"Add to Home Screen\"।", ios3: "\"Add\" dabao. Home screen se kholo.",
    pc1: "Chrome/Edge address bar me install icon (⊕ / monitor) dabao.", pc2: "Ya menu → \"Install Divya\" / \"Apps → Install this site as an app\"।",
    language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "Mic me poochhne par Divya zor se jawab deti hai", voiceFirst: "Voice-first mode", voiceFirstSub: "Har result zor se bolti hai, jawab ke baad phir sunti hai (blind users ke liye)", blindMode: "Blind Mode", blindModeSub: "Sab kuch voice se — bade buttons, high contrast, captcha guide, voice signup", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts",
    inviteTitle: "Doston ko invite karo", inviteSub: "Ek dost ke join karne par dono ko 10 lakh tokens milte hain (10 shorts ya 1× 10 minute ka video). Pool tokens kabhi expire nahi hote.", copy: "Copy", redeem: "Redeem", inviteStatus: (i, e) => `${i} invites · ${e} tokens mile`, tokSub: (w, p, v, d) => `Is hafte ${fmtTok(w)} tokens bache · pool ${fmtTok(p)} · ${v} shorts · reset ${d}`, voiceSignup: "Voice se sign up karo", voiceIncluded: "Voice assistant har plan me included hai", capDone: "Captcha solve ho gaya ✓", capNo: "Theek hai, solve nahi kiya.", capAskShot: "Captcha ka screenshot bhejo, main padhkar jawab bataungi.", blindHello: "Blind Mode on. Sab kuch voice se bataungi. Kya karna hai?",
    netErr: "Network problem. Phir try karo.", micDenied: "Mic permission do (browser settings me).", noRec: "Is browser me voice record nahi hoti.", loggedIn: n => `${n} se log in`, orDone: "OpenRouter connect ho gaya ✓", orFail: "OpenRouter connect nahi hua.",
    voicePick: "Voice (Divya ki awaaz)", voiceLoading: "Voices load ho rahi hain… (pehli baar ~90 MB download)", voiceReady: "Voices ready ✓ (Kokoro)", voiceLoadFail: "Voices load nahi hui — internet check karke phir try karo. Abhi phone voice se bol rahi hoon.", voiceRetry: "Voices phir se load karo", voiceRetryNote: "Kokoro load nahi hua — abhi sirf phone ki system voice bajegi, isliye saari voices ek jaisi sunai deti hain.", voicePlayedSystem: l => `Ye Kokoro nahi tha — phone ki system voice (${l}) se baja. Kokoro load hone par selected voice sunai degi.`, voiceNoVoice: "Voice play nahi hui — Kokoro load nahi hua, phone me voice bhi nahi hai. Internet check karo.", voiceSample: "Namaste, main Divya hoon. Main isi awaaz me bolungi.", vChild: "Bachche", vTeen: "Teenage", vAdult: "30–60", vElder: "60+ buzurg", vFemale: "Mahila", vMale: "Purush", gsAsk: "Kya main sab kuch setup karoon? Divya sab karti hai — accounts, API keys, server — aapko kuch nahi karna hai.", gsDeclined: "Theek hai, setup nahi kiya. Chat chalti rahegi — Setup screen se kabhi bhi shuru kar sakte hain.", gsStopped: "Theek hai, yahin ruk rahi hoon. Setup screen se jaari rakh sakte hain.", gsVerifyAsk: "Verification mail aa gaya hai — link ko ek baar tap karo, baaki sab Divya kar degi.", sPost: "YouTube post", postIntro: "Edit kiya video YouTube par post karo. Title, description aur tags do — schedule bhi kar sakte ho.", postVideo: "Video (job id ya link)", postJobPh: "Job id ya video link", postTitle: "Title", postDesc: "Description", postTags: "Tags (comma se alag karo)", postTagsPh: "divya, ai, video", postPrivacy: "Privacy", postSchedule: "Schedule (optional)", postThumb: "Thumbnail (optional)", postBtn: "YouTube par post karo", postDone: "Post ho gaya ✓", postViews: "Views", postLikes: "Likes", postComments: "Comments", postNeedVideo: "Video job id ya link do.", sHistory: "Mere videos", gHistory: "Mere videos", histIntro: "Edit kiye videos — video 1, video 2 number se. Upload ke liye chat me 'upload video 1' kaho.", histEmpty: "Abhi koi video nahi hai. Chat me video attach karo.", histWatch: "Dekho / Download", histUpload: "Upload karo", histDone: "Ready", histFail: "Fail ho gaya", histEditing: "Edit ho raha hai",
    setupOneTap: "One-tap setup shuru karo (ek allow)", setupConsent: "Ek allow se Divya sab kuch karti hai — accounts banana, API keys lena, captchas solve karna, server setup — sab Divya karti hai. Aapko kuch nahi karna hai.", setupHowT: "Setup kaise kaam karta hai?", setupHowDivyaT: "Divya karti hai:", setupHowDivya: "accounts banana, API keys lena, captchas solve karna, aur Cloudflare server setup karna — sab Divya karti hai, aapke ek allow se.", setupHowYouT: "Aapse sirf ek baar:", setupHowAfterT: "Uske baad:", setupHowAfter: "Setup hone par Divya chat me bata degi — uske baad Divya aapke accounts se kaam karegi.", setupHowNote: "Divya sab kuch karti hai — aapke allow se. Email link tap / SMS code ke alawa, aapko kuch nahi karna hai.", setupStepNote: "Neeche har step ki state dikhti hai: Connected = key save ho gayi ✓ · Waiting on you = sirf ek email-link tap ya SMS code chahiye · Not set = abhi nahi hua · Test failed = key kaam nahi kar rahi, phir try karo.", stepWaiting: "Aapke ek tap ka intezaar — email link ya SMS code", stepYouDo: "Ye step Divya kar rahi hai — aapko kuch nahi karna hai.", setupNeedEmail: "Naye accounts ke liye email chahiye — Profile me email set karo.", setupOpen: "Browser me kholo", setupStop: "Stop task", setupTake: "Take control", setupContinue: "Continue", setupDone: "Setup ho gaya ✓", setupRunning: "Setup chal raha hai…", setupPaused: "Ruka hua hai — aapke ek tap ka intezaar hai.", setupFailed: "Setup fail ho gaya.", setupAsk: "Kya main sab kuch setup karoon? Divya sab karti hai — accounts, API keys, server — aapko kuch nahi karna hai.", setupAllow: "Setup karo", setupDoneMsg: "Setup ho gaya ✓ — chat ab ready hai", setupStepDone: "Ho gaya ✓", setupStepRunning: "Chal raha hai…", setupStepPaused: "Aapke ek tap ke liye ruka hai", setupStepFailed: "Fail ho gaya — baaki steps se jaari hai", setupPauseEmail: "Apne email me aaye link ko ek baar tap karo — baaki sab Divya kar degi.", setupPauseSms: "Phone par aaye SMS code ko dalo — baaki sab Divya kar degi.", setupDidIt: "Maine kar diya ✓", setupPauseSignin: "Sign-in chahiye — browser me kholkar sign-in karo, phir 'Maine kar diya ✓' dabao.", setupPauseCaptcha: "Image challenge aaya hai — 'Take control' se woh ek step karo, phir continue karo.", setupStalled: "Setup ruk gaya hai — runner se update nahi aaya.", autoLogT: "Divya ne khud kya setup kiya — auto log", setupRetry: "Setup phir se chalao", openYT: "YouTube kholo", setupYouEmail: "Apne email me aaye verification link ko ek baar tap karo — baaki sab Divya kar degi.", setupYouSms: "Phone par aaye SMS code ko ek baar dalo — baaki sab Divya kar degi.", capSolving: "Captcha aa gaya hai — Divya aapke allow se khud solve kar rahi hai.", capNeedTap: "Agar image challenge hai to ek tap karo, main solve kar dungi.",
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
  showVoiceName();
  if (voiceListEl() && !voiceListEl().hidden) renderVoiceList();
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
let authTab = ["pw", "su", "wa"].includes(store.get("authTab", "pw")) ? store.get("authTab", "pw") : "pw"; // R38: a corrupt stored value used to hide every login form + throw on focus
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
  if (n.length !== 10) { $("#loginErr").textContent = t("need10"); return; }
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
const ROUTES = ["home", "chat", "voice", "connect", "setup", "plan", "download", "settings", "profile", "history"];
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
  let name = (location.hash.match(/^#\/(\w+)/) || [])[1]; if (name === "create") name = "chat"; if (!ROUTES.includes(name)) name = "home";
  const first = !cur; if (name === cur) return; cur = name;
  $$("#screens .screen").forEach(s => s.classList.toggle("active", s.id === "s-" + name));
  $$("#drawer a[data-r], #tabbar a[data-r]").forEach(a => a.dataset.r === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  name === "profile" ? $("#avatarBtn").setAttribute("aria-current", "page") : $("#avatarBtn").removeAttribute("aria-current");
  setTitle(name);
  if (!first) { $("#screen-title").focus({ preventScroll: true }); }
  announce(t("screen", t($("#s-" + name).dataset.title)));
  if (S.vf && !first && VA.state !== "speak") speak(t("screen", t($("#s-" + name).dataset.title)));
  if (name === "connect" || name === "settings") loadConnect();
  if (name === "home") loadStatus();
  if (name === "profile") { renderProfile(); loadPlan(); loadConnect(); }
  if (name === "setup") { loadKeys(); loadConnect(); }
  if (name === "history") loadVideos();
  if (name === "plan" || name === "home") loadPlan();
  if (name === "download") renderDownload();
  if (name === "chat") { scrollDown(); pollSetup(); /* R48: restore the setup mini-box if a setup is running */ }
}
window.addEventListener("hashchange", route);
const go = name => { location.hash = "#/" + name; };

/* ---------- speech locale: SR + TTS language for the current app language ---------- */
const srLang = () => S.lang === "hi" || S.lang === "hi-Latn" ? "hi-IN" : S.lang === "en" ? "en-IN" : "te-IN";
/* ---------- voices: 20 free voices (10 female + 10 male) ----------
   Per gender: 2 child, 4 teen, 2 adult (30-60), 2 elder (60+). NO robots
   (removed 2026-11-09, Ajju — replaced with 4 extra teen voices).
   EVERY voice has engine:"kokoro" with a UNIQUE Kokoro-82M voice id —
   never reuse one model for two catalog entries (the old am_adam /
   am_michael duplicates made two pairs sound identical). kokoroPitch is
   the playback-rate pitch character (child higher, elder lower);
   kokoroHi is the Hindi voice for Devanagari text (Kokoro has only 2
   Hindi voices per gender, so Hindi replies vary by voice + rate only). */
const VOICES = [
  { id: "f-child-chinni", engine: "kokoro", kokoro: "af_sky", kokoroHi: "hf_beta", name: "Chinni", gender: "F", age: "child", pitch: 1.5, rate: 1.15, kokoroPitch: 1.22 },
  { id: "f-child-bunny", engine: "kokoro", kokoro: "af_aoede", kokoroHi: "hf_alpha", name: "Bunny", gender: "F", age: "child", pitch: 1.45, rate: 1.2, kokoroPitch: 1.18 },
  { id: "f-teen-anu", engine: "kokoro", kokoro: "af_sarah", kokoroHi: "hf_alpha", name: "Anu", gender: "F", age: "teen", pitch: 1.25, rate: 1.05, kokoroPitch: 1.08 },
  { id: "f-teen-meera", engine: "kokoro", kokoro: "af_nicole", kokoroHi: "hf_beta", name: "Meera", gender: "F", age: "teen", pitch: 1.2, rate: 1.05, kokoroPitch: 1.05 },
  { id: "f-teen-isha", engine: "kokoro", kokoro: "af_jessica", kokoroHi: "hf_alpha", name: "Isha", gender: "F", age: "teen", pitch: 1.25, rate: 1.05, kokoroPitch: 1.08 },
  { id: "f-teen-tara", engine: "kokoro", kokoro: "af_alloy", kokoroHi: "hf_beta", name: "Tara", gender: "F", age: "teen", pitch: 1.2, rate: 1.05, kokoroPitch: 1.05 },
  { id: "f-adult-priya", engine: "kokoro", kokoro: "af_heart", kokoroHi: "hf_alpha", name: "Priya", gender: "F", age: "adult", pitch: 1.05, rate: 1, kokoroPitch: 1 },
  { id: "f-adult-lakshmi", engine: "kokoro", kokoro: "af_bella", kokoroHi: "hf_beta", name: "Lakshmi", gender: "F", age: "adult", pitch: 0.95, rate: 1, kokoroPitch: 0.97 },
  { id: "f-elder-ammamma", engine: "kokoro", kokoro: "af_kore", kokoroHi: "hf_alpha", name: "Ammamma", gender: "F", age: "elder", pitch: 0.8, rate: 0.9, kokoroPitch: 0.88 },
  { id: "f-elder-bamma", engine: "kokoro", kokoro: "af_river", kokoroHi: "hf_beta", name: "Bamma", gender: "F", age: "elder", pitch: 0.85, rate: 0.9, kokoroPitch: 0.92 },
  { id: "m-child-chintu", engine: "kokoro", kokoro: "am_puck", kokoroHi: "hm_psi", name: "Chintu", gender: "M", age: "child", pitch: 1.5, rate: 1.15, kokoroPitch: 1.22 },
  { id: "m-child-bunty", engine: "kokoro", kokoro: "am_eric", kokoroHi: "hm_omega", name: "Bunty", gender: "M", age: "child", pitch: 1.45, rate: 1.2, kokoroPitch: 1.18 },
  { id: "m-teen-arjun", engine: "kokoro", kokoro: "am_adam", kokoroHi: "hm_omega", name: "Arjun", gender: "M", age: "teen", pitch: 1.25, rate: 1.05, kokoroPitch: 1.08 },
  { id: "m-teen-rahul", engine: "kokoro", kokoro: "am_michael", kokoroHi: "hm_psi", name: "Rahul", gender: "M", age: "teen", pitch: 1.2, rate: 1.05, kokoroPitch: 1.05 },
  { id: "m-teen-vikram", engine: "kokoro", kokoro: "am_liam", kokoroHi: "hm_omega", name: "Vikram", gender: "M", age: "teen", pitch: 1.25, rate: 1.05, kokoroPitch: 1.08 },
  { id: "m-teen-kabir", engine: "kokoro", kokoro: "am_fenrir", kokoroHi: "hm_psi", name: "Kabir", gender: "M", age: "teen", pitch: 1.2, rate: 1.05, kokoroPitch: 1.05 },
  { id: "m-adult-ravi", engine: "kokoro", kokoro: "am_onyx", kokoroHi: "hm_omega", name: "Ravi", gender: "M", age: "adult", pitch: 0.95, rate: 1, kokoroPitch: 1 },
  { id: "m-adult-kiran", engine: "kokoro", kokoro: "am_santa", kokoroHi: "hm_psi", name: "Kiran", gender: "M", age: "adult", pitch: 0.9, rate: 1, kokoroPitch: 0.97 },
  { id: "m-elder-tatayya", engine: "kokoro", kokoro: "bm_george", kokoroHi: "hm_omega", name: "Tatayya", gender: "M", age: "elder", pitch: 0.75, rate: 0.85, kokoroPitch: 0.88 },
  { id: "m-elder-pedda", engine: "kokoro", kokoro: "bm_lewis", kokoroHi: "hm_psi", name: "Pedda Nanna", gender: "M", age: "elder", pitch: 0.8, rate: 0.9, kokoroPitch: 0.92 },
];
const voiceById = id => VOICES.find(v => v.id === id) || VOICES.find(v => v.id === "f-adult-priya");
const ageLabel = a => t({ child: "vChild", teen: "vTeen", adult: "vAdult", elder: "vElder" }[a]);
function showVoiceName() { $$(".voiceName").forEach(e => e.textContent = voiceById(S.voiceId).name); }
/* Picker status line: Kokoro load state, so a silent voice is never a mystery. */
function voiceStatusText() {
  const st = typeof kokoroStatus === "function" ? kokoroStatus() : { state: "unknown" };
  if (st.state === "ready") return t("voiceReady");
  if (st.state === "failed") return t("voiceLoadFail");
  if (st.state === "loading") return t("voiceLoading");
  return t("voiceLoading");
}
function renderVoiceList() {
  const el = $("#voiceList"); if (!el) return;
  const group = g => `<h3 class="h3">${g === "F" ? t("vFemale") : t("vMale")}</h3>` + VOICES.filter(v => v.gender === g).map(v => `<div class="row"><button class="btn" style="flex:1;text-align:left" data-vid="${v.id}">${v.name} · <span class="muted small">${ageLabel(v.age)}</span>${S.voiceId === v.id ? " ✓" : ""}</button><button class="btn secondary" data-play="${v.id}" aria-label="Sample">▶</button></div>`).join("");
  const kst = typeof kokoroStatus === "function" ? kokoroStatus() : { state: "unknown" };
  el.innerHTML = `<p class="muted small" id="voiceStatus">${voiceStatusText()}</p>` +
    // v37: when Kokoro failed, say so and offer a retry — the old list just
    // sat there while every sample silently played the one phone voice.
    (kst.state === "failed" ? `<button class="btn secondary" id="voiceRetry" type="button">${esc(t("voiceRetry"))}</button><p class="muted small">${esc(t("voiceRetryNote"))}</p>` : "") +
    group("F") + group("M");
  const retry = $("#voiceRetry");
  if (retry) retry.onclick = () => {
    if (typeof kokoroRetry === "function") kokoroRetry();
    retry.disabled = true; retry.textContent = t("voiceLoading");
    warmVoices(); renderVoiceList();
  };
  refreshVoiceStatus(); // status line only — never rebuild the list while loading (taps were swallowed by the rebuild)
}
/* R38: while Kokoro loads, refresh ONLY the status line text every 3s. The old
   code re-rendered the whole voice list, rebuilding the buttons under the user's
   finger mid-tap. Stops by itself once the model is ready/failed or the list closes. */
function refreshVoiceStatus() {
  const st = $("#voiceStatus"); if (!st || $("#voiceList").hidden) return;
  st.textContent = voiceStatusText();
  if (typeof kokoroStatus === "function" && kokoroStatus().state === "loading") {
    clearTimeout(refreshVoiceStatus._t); refreshVoiceStatus._t = setTimeout(refreshVoiceStatus, 3000);
  }
}

/* ---------- speech out ----------
   Kokoro (real audio playback) is the PRIMARY path for ALL 20 voices.
   The phone's system TTS is only an ANNOUNCED fallback: if Kokoro cannot
   load, the UI says so (toast + picker status) instead of silently falling
   back to a system voice that may itself be silent (empty getVoices() on
   Android / Capacitor WebView) — that silent fallthrough is why voices
   "didn't play at all". */
let voices = []; const loadVoices = () => voices = speechSynthesis?.getVoices() || [];
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
/* Wait for the system voice list to populate (Android often returns [] on
   first call, and voiceschanged may fire late or never in a WebView). */
function waitVoices(ms = 2000) {
  return new Promise(res => {
    if (!("speechSynthesis" in window)) return res([]);
    if (speechSynthesis.getVoices().length) { loadVoices(); return res(voices); }
    let done = false; const fin = () => { if (!done) { done = true; loadVoices(); res(voices); } };
    const prev = speechSynthesis.onvoiceschanged;
    speechSynthesis.onvoiceschanged = () => { loadVoices(); if (prev) prev(); fin(); };
    setTimeout(fin, ms);
  });
}
/* Toast that never speaks (speak() uses it for its own failures — a speaking
   toast there would recurse forever). */
function toastPlain(msg) { const e = $("#toast"); e.textContent = msg; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 4000); }
let _voiceFailToastAt = 0;
function announceVoiceFail(key) {
  const now = Date.now(); if (now - _voiceFailToastAt < 30000) return; _voiceFailToastAt = now;
  toastPlain(t(key)); const st = $("#voiceStatus"); if (st) st.textContent = t(key);
}
/* v37: what actually played last — { engine: "kokoro" | "system" | "none", label }.
   The voice picker reads speak.last so a sample never pretends to be the
   selected Kokoro voice when the phone system voice played instead. */
function speak(text, ov, opts) {
  return new Promise(async res => {
    const fin = ok => res(!!ok);
    const clean = String(text || "").replace(/https?:\/\/\S+/g, "").replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "").replace(/[✓•…]/g, " ").trim(); if (!clean) return fin(true);
    const pick = ov || voiceById(S.voiceId);
    // Previews may wait longer for the model (opts.waitMs); replies keep the
    // 25s default so a slow download never stalls a voice reply for minutes.
    const waitMs = (opts && opts.waitMs) || 25000;
    const setLast = (engine, label) => { speak.last = { engine, label: label || "" }; };
    // Primary: Kokoro. Wait for an in-flight model load (shared promise), but
    // never hang forever — waitMs, then fail honestly.
    if (pick.engine === "kokoro" && typeof kokoroPlay === "function") {
      try {
        await Promise.race([kokoroPlay(clean, pick), new Promise((_, rej) => setTimeout(() => rej(new Error("kokoro timeout")), waitMs))]);
        setLast("kokoro", pick.name + " · " + (typeof kokoroVoiceFor === "function" ? kokoroVoiceFor(pick, clean) : (pick.kokoro || "")));
        return fin(true);
      } catch (e) {
        announceVoiceFail("voiceLoadFail");
        // fall through to the system voice — announced, not silent
      }
    } else if (pick.engine === "kokoro") {
      announceVoiceFail("voiceLoadFail"); // voices-kokoro.js itself failed to load
    }
    // Fallback: system TTS — only if a real voice exists. Never speak into the void.
    if (!("speechSynthesis" in window)) { setLast("none"); announceVoiceFail("voiceNoVoice"); return fin(false); }
    const list = await waitVoices();
    const isTe = /[\u0C00-\u0C7F]/.test(clean), isHi = /[\u0900-\u097F]/.test(clean);
    const want = isTe ? ["te-IN"] : isHi ? ["hi-IN"] : (S.lang === "hi" || S.lang === "hi-Latn") ? ["hi-IN", "en-IN"] : ["en-IN", "hi-IN", "en-GB", "en-US"];
    if (!list.length) { setLast("none"); announceVoiceFail("voiceNoVoice"); return fin(false); }
    const u = new SpeechSynthesisUtterance(clean);
    const fem = /female|heera|veena|neerja|swara|kalpana|zira|samantha|google/i;
    // v37: the old fallback picked the FIRST voice of the gender for all 10
    // catalog voices of that gender — every female sample sounded identical,
    // and on phones with a single en-IN voice, literally one voice for all 20.
    // Spread catalog voices across the real system voices (same gender first)
    // so fallback samples still differ, and keep each voice's own pitch/rate.
    let v = null;
    for (const l of want) {
      const c = list.filter(x => x.lang.replace("_", "-") === l);
      if (!c.length) continue;
      const same = c.filter(x => pick.gender === "F" ? fem.test(x.name) : !fem.test(x.name));
      const pool = same.length ? same : c;
      v = pool[Math.max(0, VOICES.findIndex(x => x.id === pick.id)) % pool.length];
      break;
    }
    if (v) { u.voice = v; u.lang = v.lang; setLast("system", v.name + " (" + v.lang + ")"); } else { u.lang = isTe ? "te-IN" : isHi ? "hi-IN" : srLang(); setLast("system", "system"); }
    u.rate = pick.rate; u.pitch = pick.pitch;
    let done = false; const done1 = ok => { if (!done) { done = true; fin(ok); } };
    u.onend = () => done1(true); u.onerror = () => done1(false);
    setTimeout(() => done1(false), Math.min(30000, 1500 + clean.length * 90));
    // Android race: cancel() right before speak() can cancel the new utterance
    // too — only cancel when something is actually speaking, and wait for it.
    if (speechSynthesis.speaking || speechSynthesis.pending) { try { speechSynthesis.cancel(); } catch {} await new Promise(r => setTimeout(r, 120)); }
    try { speechSynthesis.speak(u); } catch { done1(false); }
  });
}
speak.last = { engine: "none", label: "" };
/* Warm the Kokoro model in the background (after login) so the first voice
   reply doesn't wait on a ~90 MB download; the picker status line shows the
   real state. Fire-and-forget — failures surface via the status line. */
function warmVoices() {
  if (typeof kokoroWarm === "function") {
    kokoroWarm().then(() => { const st = $("#voiceStatus"); if (st && !$("#voiceList").hidden) renderVoiceList(); })
      .catch(() => { const st = $("#voiceStatus"); if (st && !$("#voiceList").hidden) renderVoiceList(); });
  }
}
/* ---------- voice picker UI (Settings) ---------- */
const voiceListEl = () => $("#voiceList");
$("#voiceRow") && ($("#voiceRow").onclick = () => { const el = voiceListEl(); if (!el) return; renderVoiceList(); el.hidden = !el.hidden; });
voiceListEl() && voiceListEl().addEventListener("click", async e => {
  const play = e.target.closest("[data-play]");
  // v24: the Sample button must show it is playing, and say so plainly when
  // it cannot play (the test saw a silent tap with no feedback at all).
  if (play) {
    const label = play.textContent; play.textContent = "⏸"; play.disabled = true;
    // v37: previews wait for the real Kokoro model — the first download is
    // ~90 MB and can take over a minute on mobile data, and the old 25s
    // timeout fell back to the single phone voice mid-download. If the phone
    // voice still plays, the toast names it instead of pretending it is the
    // selected voice.
    const ok = await speak(t("voiceSample"), voiceById(play.dataset.play), { waitMs: 120000 });
    play.textContent = label; play.disabled = false;
    const last = speak.last || {};
    if (!ok) toast(t("voiceLoadFail"), true);
    else if (last.engine === "system") toast(t("voicePlayedSystem", last.label || ""), true);
    return;
  }
  const sel = e.target.closest("[data-vid]");
  if (sel) {
    S.voiceId = sel.dataset.vid; store.set("voiceId", S.voiceId); showVoiceName(); renderVoiceList();
    const ok = await speak(t("voiceSample"), undefined, { waitMs: 120000 });
    const last = speak.last || {};
    if (!ok) toast(t("voiceLoadFail"), true);
    else if (last.engine === "system") toast(t("voicePlayedSystem", last.label || ""), true);
  }
});
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
/* R28+R33: openUrl returns what ACTUALLY happened — never claim an open that did not happen.
   "opened" = new tab opened (https); "navigated" = left Divya for the dialer (tel:);
   "blocked" = browser blocked the popup, nothing opened; "off" = auto-open disabled.
   Intent URLs are APP-FIRST: the native app opens when installed; the browser
   fallback (S.browser_fallback_url) fires ONLY when the app is missing. openIntent
   detects the outcome instead of guessing it:
   - window.open returns null + page hides within 1.5s => the app took over ("app")
   - window.open returns a window that closes quickly => transient tab, app opened ("app")
   - window.open returns a window that stays open => fallback tab in the browser ("browser")
   - window.open returns null + page stays visible => popup blocked; last resort is a
     same-tab intent navigation — if the app opens, visibility fires ("app"); if the
     fallback opens, this tab is replaced by the browser page and no reply is ever
     shown, so no false claim is possible. */
function openUrl(url) {
  if (store.get("noauto", false)) return "off";
  if (/^tel:/.test(url)) { location.href = url; return "navigated"; }
  if (/^intent:/.test(url)) return openIntent(url); // async Promise<"app"|"browser"|"blocked">
  let w = null;
  try { w = window.open(url, "_blank", "noopener"); } catch {}
  if (w) return "opened";
  return "blocked"; // do NOT navigate away; the reply shows a tap-to-open link instead
}
function openIntent(url) {
  return new Promise(res => {
    let done = false;
    const finish = r => { if (done) return; done = true; document.removeEventListener("visibilitychange", onVis); res(r); };
    const onVis = () => { if (document.hidden) finish("app"); };
    document.addEventListener("visibilitychange", onVis);
    let w = null;
    try { w = window.open(url, "_blank", "noopener"); } catch {}
    if (!w) {
      if (document.hidden) return finish("app");
      setTimeout(() => {
        if (document.hidden) return finish("app");
        location.href = url; // last resort: same-tab intent (popup blockers do not stop it)
        setTimeout(() => finish("blocked"), 1200);
      }, 1500);
      return;
    }
    const t0 = Date.now();
    const iv = setInterval(() => {
      let closed = false;
      try { closed = w.closed; } catch { closed = true; }
      if (closed) { clearInterval(iv); finish("app"); }
      else if (Date.now() - t0 > 1500) { clearInterval(iv); finish("browser"); }
    }, 150);
  });
}
function openSay(host, r) { return r === "opened" ? t("openedTab", host) : r === "navigated" ? t("openedApp", host) : r === "off" ? t("openOff", host) : t("openBlocked", host); }
function ytUrl(q) { const web = "https://www.youtube.com/results?search_query=" + encodeURIComponent(q); return isAndroid ? `intent://www.youtube.com/results?search_query=${encodeURIComponent(q)}#Intent;scheme=https;package=com.google.android.youtube;S.browser_fallback_url=${encodeURIComponent(web)};end` : web; }
// R32: plain "open YouTube" uses the same app intent as play — the YouTube app, not the browser.
function ytAppUrl() { const web = "https://www.youtube.com"; return isAndroid ? `intent://www.youtube.com/#Intent;scheme=https;package=com.google.android.youtube;S.browser_fallback_url=${encodeURIComponent(web)};end` : web; }
function openYTSay(r) { if (r === "app") return t("openYTApp"); if (r === "browser") return t("ytNoApp"); if (r === "blocked") return t("openBlocked"); if (r === "off") return t("openOff"); return t("ytOpening"); }
// R33: WhatsApp gets the same app-first treatment — native app when installed,
// browser (wa.me) only when the app is missing.
function waIntentUrl(num, text) { const web = `https://wa.me/${num}?text=${encodeURIComponent(text || "")}`; return isAndroid ? `intent://wa.me/${num}?text=${encodeURIComponent(text || "")}#Intent;scheme=https;package=com.whatsapp;S.browser_fallback_url=${encodeURIComponent(web)};end` : web; }
function openWaSay(r) { if (r === "app") return t("waApp"); if (r === "browser") return t("waNoApp"); if (r === "blocked") return t("openBlocked"); if (r === "off") return t("openOff"); return t("waOpening"); }
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
    const num = a.number || findContact(a.name); const url = num ? waIntentUrl(num, a.text) : `https://wa.me/?text=${encodeURIComponent(a.text || "")}`;
    out.buttons.push({ label: t("waBtn"), href: url }); out.auto = async () => { const r = await openUrl(url); out.say = num ? openWaSay(r) : openSay("WhatsApp", r); };
    if (!num && a.name) addContactButtons(out, a, true);
  } else if (a.type === "open") { const host = new URL(a.url).hostname.replace(/^www\./, ""); const isYT = /^youtube\.com$/.test(host); const href = isYT ? ytAppUrl() : a.url; out.buttons.push({ label: t("openBtn", host), href }); out.auto = async () => { const r = await openUrl(href); out.say = isYT ? openYTSay(r) : openSay(host, r); }; }
  else if (a.type === "play") { const u = ytUrl(a.query || ""); out.buttons.push({ label: t("playBtn"), href: u }); out.auto = async () => { const r = await openUrl(u); out.say = openYTSay(r); }; }
  else if (a.type === "reminder") { addReminder(a.at, a.text); out.buttons.push({ label: t("calBtn"), href: calUrl(a.at, a.text), alt: true }); }
  else if (a.type === "subscribe") out.buttons.push({ label: t("subBtn"), href: "#/plan" });
  else if (a.type === "route" && ROUTES.includes(a.to)) { out.buttons.push({ label: t("s" + a.to[0].toUpperCase() + a.to.slice(1)), href: "#/" + a.to }); out.auto = () => go(a.to); }
  return out;
}
function addContactButtons(out, a, alt) {
  if (navigator.contacts?.select) out.buttons.push({ label: t("pickContact"), alt: true, fn: async () => { try { const [c] = await navigator.contacts.select(["name", "tel"], { multiple: false }); const n = normNum(c?.tel?.[0]); if (n) { saveContact(a.name, n); pendingContact = null; runAction({ ...a, number: n }, true); } } catch {} } });
  out.buttons.push({ label: t("typeNumber"), alt: true, fn: () => { const v = prompt(t("askNumber", a.name)); const n = normNum(v); if (n) { saveContact(a.name, n); pendingContact = null; runAction({ ...a, number: n }, true); } } });
}
async function runAction(a, auto) { const p = planAction(a); if (auto && p.auto) await p.auto(); return p; }
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
  let d = await api("assist", { method: "POST", json: { text, tz, voiceId: S.voiceId, ...(c ? { lat: c.lat, lon: c.lon } : {}) } });
  if (d.need === "location") { const g = await getCoords(); if (g) d = await api("assist", { method: "POST", json: { text, tz, voiceId: S.voiceId, lat: g.lat, lon: g.lon } }); }
  return d;
}
/* R40: chat-first video — a video attached in chat rides with the message as
   [[EDITVIDEO: <staged job>]] (server strips it). The user only ever sees
   their own words. R47: template picking removed — Divya chooses the
   aesthetic itself. */
let pendingVideo = null;
function showChip() {
  const c = $("#attachChip"); if (!c) return;
  const parts = [];
  if (pendingVideo) parts.push("\uD83D\uDCCE " + pendingVideo.name + " · " + t("attachChatNote"));
  if (!parts.length) { c.hidden = true; return; }
  $("#attachChipTxt").textContent = parts.join(" \u00b7 "); c.hidden = false;
}
$("#attachChipX").onclick = () => { pendingVideo = null; showChip(); updateBtn(); };
let busy = false;
async function send(text) {
  text = (text || "").trim();
  if ((!text && !pendingVideo) || busy) return;
  if (!text && pendingVideo) text = t("attachVideoMsg");
  busy = true; bubble("user", text); $("#input").value = ""; autoGrow(); updateBtn(); typing(true);
  let serverText = text;
  if (pendingVideo) serverText += `\n[[EDITVIDEO: ${pendingVideo.job}]]`;
  pendingVideo = null; showChip();
  try {
    const d = await assist(serverText);
    let reply = String(d.reply || "");
    reply = reply.replace(/\[\[TEMPLATES\]\]/g, "").trim();
    if (!d.ok && !reply) { typing(false); bubble("bot", d.error || t("netErr")); }
    else { const p = await runAction(d.action, true); typing(false); bubble("bot", reply + (p.say ? "\n" + p.say : ""), { buttons: p.buttons }); if (S.vf) speak(reply + (p.say ? " " + p.say : "")); if (d.video_started) { toast(t("started")); if (d.video_num != null && d.video_job) pollChatVideo(d.video_num, d.video_job); } }
  } catch (e) { typing(false); if (e.message !== "login") { bubble("sys", t("netErr")); checkSetupPrompt(true); /* R48 item 5: chat failed + setup still needed -> offer setup again, not a dead-end */ } }
  busy = false; saveChat();
}
/* R42: in-chat video delivery, Hark-style — when a video starts, poll History
   until it is done, then drop the finished video right into this chat. */
let chatPoll = null;
function videoBubble(num, url) {
  const el = $("#msgs"); if (!el) return;
  $("#msgs .empty")?.remove();
  const d = document.createElement("div"); d.className = "msg bot";
  d.innerHTML = `<b>${esc(t("jobDone"))} — video ${num}</b><video controls preload="metadata" playsinline src="${url}" style="width:100%;border-radius:12px;margin-top:6px"></video><br><a href="${url}" download="divya-video-${num}.mp4">${esc(t("histWatch"))}</a>`;
  el.appendChild(d); scrollDown(); saveChat();
}
function videoBubbleFail(num) { bubble("bot", `${t("jobFail")} — video ${num}`); saveChat(); }
async function pollChatVideo(num, job) {
  if (chatPoll) clearInterval(chatPoll);
  let tries = 0;
  const tick = async () => {
    if (++tries > 90) { clearInterval(chatPoll); chatPoll = null; return; }
    let v = null;
    try { const d = await api("videos"); v = (d.videos || []).find(x => x.job === job || x.n === num); } catch {}
    if (!v) return;
    if (v.state === "failed") { clearInterval(chatPoll); chatPoll = null; videoBubbleFail(num); return; }
    if (v.state === "done" && v.has_result) {
      clearInterval(chatPoll); chatPoll = null;
      try {
        const r = await apiFetch("result?job=" + job, { headers: { authorization: "Bearer " + S.token } });
        if (!r.ok) { videoBubbleFail(num); return; }
        videoBubble(num, URL.createObjectURL(await r.blob()));
      } catch { videoBubbleFail(num); }
    }
  };
  tick();
  chatPoll = setInterval(tick, 10000);
}
/* R48: one-tap setup + Muse-style background browser mini-box in chat. */
/* v39 Phase 2: visible auto-provisioning log — what Divya did on its own
   (when / which provider / why / result). Fed by setup/status autoLog. */
let lastAutoLog = [];
function renderAutoLog() {
  const ul = $("#autoLog"); if (!ul) return;
  const card = $("#autoLogCard"); if (card) card.hidden = !lastAutoLog.length;
  ul.innerHTML = lastAutoLog.map(e => {
    const when = e.at ? new Date(e.at).toLocaleString() : "";
    const who = e.provider ? ((KP[e.provider] && KP[e.provider].name) || e.provider) + ": " : "";
    return `<li class="muted small">${esc(when)} — ${esc(who + (e.action || ""))}${e.why ? " — " + esc(e.why) : ""} (${esc(e.result || "")})</li>`;
  }).join("");
}
let setupPoll = null, setupBoxEl = null;
/* v39: the one-tap button works ONLY with the permission box ticked
   (the live test proved it started without consent). The button stays
   disabled until ticked; tapping it unticked (or via any other entry
   point) opens the allow sheet instead of starting the setup. */
function syncOneTapBtn() { const b = $("#oneTapBtn"); if (b) b.disabled = !S.consent; }
async function startOneTapSetup() {
  if (!S.consent) { if (!needConsent(() => startOneTapSetup())) return; return; }
  const btn = $("#oneTapBtn"); if (btn) btn.disabled = true;
  try {
    let email = "";
    try { const me = await api("me"); email = (me.account && me.account.email) || ""; } catch {}
    if (!email) { toast(t("setupNeedEmail"), true); return; }
    const d = await api("setup/start", { method: "POST", json: { email, providers: ["groq", "openrouter", "gemini"] } });
    // R48 note: Cloudflare stays out of this list until setup.py has a
    // Cloudflare flow (FLOWS has only email/google flows today) — starting it
    // now would stall the chain. The mini-box still renders a Cloudflare step
    // when setup/status reports one.
    if (!d.ok) { toast(d.error || t("netErr"), true); return; }
    location.hash = "#/chat";
    bubble("bot", t("setupRunning"));
    pollSetup();
  } finally { syncOneTapBtn(); }
}
/* R48 mini-box: renders the steps[] array from setup/status, one row per step
   (Groq / OpenRouter / Gemini / Cloudflare server) with its state — done ✓,
   running…, paused for the user's one tap, or failed (moves on with the
   rest). Falls back to the pre-v38 shape {current:{site,step,note,url,state},
   providers, done}. A paused step shows the one plain line (email-link tap
   or SMS code) plus a "Nenu chesa ✓" button that resumes via setup/continue. */
let setupPause = null; // {id} of the step paused for the user's one tap (email/SMS only)
function setupStepLabel(st) {
  const name = st.name || (KP[st.id] && KP[st.id].name) || st.id || st.site || "";
  const state = String(st.state || "").toLowerCase();
  const queued = state === "queued" || state === "pending" || state === "waiting";
  const mark = state === "done" ? "✓ " : state === "paused" ? "⏸ " : state === "failed" ? "✗ " : queued ? "· " : "… ";
  const word = state === "done" ? t("setupStepDone") : state === "paused" ? t("setupStepPaused") : state === "failed" ? t("setupStepFailed") : queued ? t("stepNot") : t("setupStepRunning");
  return `<div class="muted small">${esc(mark + name + ": " + word)}${st.note ? " — " + esc(st.note) : ""}</div>`;
}
function renderSetupBox(d) {
  const steps = Array.isArray(d.steps) ? d.steps : null;
  const cur = d.current;
  if (!steps && !cur) return;
  if (!setupBoxEl || !document.body.contains(setupBoxEl)) {
    $("#msgs .empty")?.remove();
    setupBoxEl = document.createElement("div");
    setupBoxEl.className = "msg bot setup-box";
    $("#msgs").appendChild(setupBoxEl);
  }
  const state = String(d.state || (cur && cur.state) || (d.active ? "running" : "")).toLowerCase();
  const done = state === "done";
  const failed = state === "failed" || state === "stopped";
  const stalled = state === "stalled";
  const pausedStep = steps ? steps.find(s => String(s.state || "").toLowerCase() === "paused") : (cur && cur.state === "paused" ? cur : null);
  const title = done ? t("setupDone") : stalled ? t("setupStalled") : failed ? t("setupFailed") : pausedStep ? t("setupPaused") : t("setupRunning");
  // "Waiting on you" lives ONLY on the paused step (email link / SMS code).
  const newPause = pausedStep ? { id: pausedStep.id || pausedStep.provider || "" } : null;
  if (JSON.stringify(newPause) !== JSON.stringify(setupPause)) { setupPause = newPause; if (cur === "setup") renderSteps(); }
  let html = `<b>${esc(title)}</b>`;
  if (steps) {
    html += steps.map(setupStepLabel).join("");
    if (pausedStep) {
      // v39: every pause kind gets its own plain line — signin (open the
      // provider page and sign in) and captcha included, not just email/SMS.
      const kind = String(pausedStep.kind || pausedStep.pause || "").toLowerCase();
      const line = kind === "sms" || kind === "phone" || kind === "code" ? t("setupPauseSms")
        : kind === "signin" ? t("setupPauseSignin")
        : kind === "captcha" ? t("setupPauseCaptcha")
        : t("setupPauseEmail");
      html += `<div>${esc(line)}</div>`;
    }
    if (stalled && d.finished && d.finished.note) html += `<div class="muted small">${esc(d.finished.note)}</div>`;
  } else {
    html += `<div class="muted small">${esc(cur.site || "")} · ${esc(cur.step || "")}</div>` +
      (cur.note ? `<div>${esc(cur.note)}</div>` : "") +
      `<div class="muted small">${esc((d.providers || []).join(" → "))}${d.done && d.done.length ? " · ✓ " + d.done.join(", ") : ""}</div>`;
  }
  // v39: the sign-in page to open comes from the server's action (or the
  // current job's URL) — a paused-signin step without an open button is
  // exactly the bug the live test caught.
  const actionUrl = (d.action && d.action.url) || (cur && cur.url) || "";
  html += `<div class="act">` +
    (actionUrl ? `<button class="pill" data-a="open">${esc(t("setupOpen"))}</button>` : "") +
    (pausedStep ? `<button class="pill" data-a="done">${esc(t("setupDidIt"))}</button>` : "") +
    (cur && cur.state === "paused" && !pausedStep ? `<button class="pill" data-a="continue">${esc(t("setupContinue"))}</button>` : "") +
    ((failed || stalled) ? `<button class="pill" data-a="retry">${esc(t("setupRetry"))}</button>` : "") +
    `<button class="pill" data-a="take">${esc(t("setupTake"))}</button>` +
    `<button class="pill" data-a="stop">${esc(t("setupStop"))}</button></div>`;
  setupBoxEl.innerHTML = html;
  const open = setupBoxEl.querySelector('[data-a="open"]');
  if (open) open.onclick = () => { if (actionUrl) window.open(actionUrl, "_blank"); };
  const didIt = setupBoxEl.querySelector('[data-a="done"]');
  if (didIt) didIt.onclick = async () => { await api("setup/continue", { method: "POST", json: {} }); pollSetup(); };
  const retry = setupBoxEl.querySelector('[data-a="retry"]');
  if (retry) retry.onclick = () => startOneTapSetup();
  const take = setupBoxEl.querySelector('[data-a="take"]');
  if (take) take.onclick = async () => { const kind = (pausedStep && (pausedStep.kind || pausedStep.pause)) || "signin"; await api("setup/pause", { method: "POST", json: { reason: String(kind).toLowerCase() } }); if (actionUrl) window.open(actionUrl, "_blank"); pollSetup(); };
  const stop = setupBoxEl.querySelector('[data-a="stop"]');
  if (stop) stop.onclick = async () => { await api("setup/stop", { method: "POST", json: {} }); pollSetup(); };
  const cont = setupBoxEl.querySelector('[data-a="continue"]');
  if (cont) cont.onclick = async () => { await api("setup/continue", { method: "POST", json: {} }); pollSetup(); };
  scrollDown();
}
async function pollSetup() {
  if (setupPoll) clearInterval(setupPoll);
  let tries = 0;
  const tick = async () => {
    // v39: the poll itself must never die silently. 30 min with no
    // terminal state means the run is stalled — show that + Retry in the
    // box (and in chat) instead of leaving "Setup running…" on screen.
    if (++tries > 360) { clearInterval(setupPoll); setupPoll = null; setupShowStalled(); return; } // 30 min
    let d = null;
    try { d = await api("setup/status"); } catch {}
    if (!d || !d.ok) return;
    if (Array.isArray(d.autoLog)) { lastAutoLog = d.autoLog; renderAutoLog(); }
    // v38 shape carries d.state ("done"/"running"/"paused"/"failed"); pre-v38
    // shape carries d.finished. Either way, a finished run ends polling.
    // v39: "stalled" is terminal too.
    const state = String(d.state || (d.finished && d.finished.state) || "").toLowerCase();
    if (!d.active && (state === "done" || state === "failed" || state === "stalled" || d.finished)) {
      clearInterval(setupPoll); setupPoll = null;
      if (state === "done") {
        // R48: done means the mini-box closes and chat is ready — one plain line.
        if (setupBoxEl && document.body.contains(setupBoxEl)) { setupBoxEl.remove(); setupBoxEl = null; }
        setupPause = null;
        bubble("bot", t("setupDoneMsg")); saveChat();
        return;
      }
      // v24: the setup ended — show the final state (done/failed) as a chat
      // message so it survives redraws, instead of the box just vanishing.
      if (d.finished && setupBoxEl && document.body.contains(setupBoxEl)) {
        const f = d.finished;
        const doneKeys = (f.done || []).filter(id => d.keys && d.keys[id]);
        const stalled = state === "stalled" || f.state === "stalled";
        const title = stalled ? t("setupStalled") : t("setupFailed");
        const line = f.state === "done"
          ? `${t("setupDone")} — ${doneKeys.length ? "✓ " + doneKeys.join(", ") : (f.done || []).join(", ")}`
          : `${title} — ${(f.done || []).join(", ")}${f.provider ? " (" + f.provider + ": " + (f.note || "") + ")" : ""}`;
        setupBoxEl.innerHTML = `<b>${esc(title)}</b><div>${esc(line)}</div><div class="act"><button class="pill" data-a="retry">${esc(t("setupRetry"))}</button></div>`;
        setupBoxEl.querySelector('[data-a="retry"]').onclick = () => startOneTapSetup();
        bubble("bot", line); saveChat();
        setupBoxEl = null;
      }
      return;
    }
    if (d.active || d.steps || d.current) renderSetupBox(d);
  };
  tick();
  setupPoll = setInterval(tick, 5000);
}
/* v39: app-side backstop when polling itself times out with no terminal
   state from the server — render the box as stalled with Retry, and say
   so in chat. (The server watchdog normally fires first, at 10 min.) */
function setupShowStalled() {
  if (setupBoxEl && document.body.contains(setupBoxEl)) {
    setupBoxEl.innerHTML = `<b>${esc(t("setupStalled"))}</b><div>${esc(t("setupStalled"))}</div><div class="act"><button class="pill" data-a="retry">${esc(t("setupRetry"))}</button></div>`;
    setupBoxEl.querySelector('[data-a="retry"]').onclick = () => startOneTapSetup();
    setupBoxEl = null;
  }
  bubble("bot", t("setupStalled")); saveChat();
}
$("#oneTapBtn").onclick = () => startOneTapSetup();
syncOneTapBtn(); // v39: disabled until the permission box is ticked
const input = $("#input");
function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
function updateBtn() { $("#chatSend").disabled = !input.value.trim() && !pendingVideo; }
$("#chatSend").onclick = () => send(input.value);
input.addEventListener("input", () => { autoGrow(); updateBtn(); });
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && matchMedia("(pointer:fine)").matches) { e.preventDefault(); send(input.value); } });
$("#composer").onsubmit = e => { e.preventDefault(); send(input.value); };

/* image + video attach (R40: a video stages in chat, then rides with the message) */
$("#attach").onclick = () => $("#file").click();
$("#file").onchange = async e => {
  const f = e.target.files[0]; e.target.value = ""; if (!f || busy) return;
  if (f.type && f.type.startsWith("video/")) {
    if (f.size > 24 * 1048576) { toast(t("tooBig"), true); return; }
    busy = true; typing(true);
    try {
      const fd = new FormData(); fd.append("stage", "1"); fd.append("video", f, f.name);
      const d = await xhrUpload("edit", fd, () => {});
      if (d.ok && d.staged) { pendingVideo = { job: d.staged, name: f.name }; showChip(); updateBtn(); }
      else toast(d.error || t("netErr"), true);
    } catch (x) { if (x.message !== "login") toast(t("netErr"), true); }
    typing(false); busy = false; return;
  }
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
  const fd = new FormData(); fd.append("audio", blob, "voice." + ext); fd.append("lang", S.lang); fd.append("assist", "1"); fd.append("tz", tz); fd.append("voiceId", S.voiceId);
  if (coords) { fd.append("lat", coords.lat); fd.append("lon", coords.lon); }
  busy = true;
  if (recTarget === "chat") {
    const me = bubble("user", "🎙️ …"); typing(true);
    try {
      const d = await api("voice", { method: "POST", form: fd });
      if (d.heard) { me.innerHTML = `<span class="heard" aria-hidden="true">🎙️</span>` + linkify(d.heard); const p = await runAction(d.action, true); typing(false); bubble("bot", (d.reply || d.error || "") + (p.say ? "\n" + p.say : ""), { buttons: p.buttons }); if (S.voice || S.vf) speak((d.reply || "") + " " + (p.say || "")); if (d.video_started) toast(t("started")); }
      else { typing(false); me.remove(); bubble("sys", d.error || t("netErr")); }
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
holdable(micBtn, "chat", false); // R32: mic stays mic — sending is #chatSend's job now
// keyboard / screen-reader double-tap on the chat mic: start voice assistant listening instead of hold
micBtn.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && micBtn.classList.contains("mic")) { e.preventDefault(); go("voice"); setTimeout(() => vaOnce(), 300); } });

/* ---------- "Hey Divya" voice assistant ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const WAKE = /\b(?:hey|hi|hay|he|ok|okay|ఓకే|హే|హాయ్)[\s,]*(?:divya|diviya|divyaa|dhivya|divia|దివ్య|దివ్యా)\b|(?:హే|హాయ్)\s*దివ్యా?/i;
const VA = { on: false, state: "idle", r: null, cmdTimer: 0, once: false, followUp: false };
function setVState(s) {
  VA.state = s; const o = $("#orb"); if (o) o.dataset.state = s;
  const txt = { idle: SR ? t("vIdle") : t("vNoSR"), wake: t("vWake"), listen: t("vListen"), think: t("vThink"), speak: t("vSpeak") }[s] || "";
  $("#vState").textContent = txt; const wd = $("#wakeDot"); if (wd) wd.hidden = !(VA.on && s === "wake");
}
const vaIdleState = () => VA.on ? "wake" : "idle";
function vaKill() { if (VA.r) { VA.r.onend = null; VA.r.onresult = null; VA.r.onerror = null; try { VA.r.abort(); } catch {} VA.r = null; } clearTimeout(VA.cmdTimer); }
function vaListen(mode) {
  if (!SR || document.hidden || $("#main").hidden) return;
  vaKill(); const r = new SR(); VA.r = r;
  r.lang = srLang(); r.continuous = true; r.interimResults = true; r.maxAlternatives = 1;
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
  const p = await runAction(d.action, true); const reply = (d.reply || d.error || t("netErr")) + (p.say ? " " + p.say : "");
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

/* ---------- templates: visual cards (R25) — same palette as video-kit/render.py ---------- */
/* R47: template cards removed — Divya chooses the aesthetic itself, the user
   never picks a template. (TEMPLATES_UI / renderTplCards deleted.) */

/* ---------- video history (R22) ---------- */
async function watchJob(job) {
  try {
    const r = await apiFetch("result?job=" + job, { headers: { authorization: "Bearer " + S.token } });
    if (!r.ok) { toast(t("netErr"), true); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = url; a.download = `divya-edit-${job}.mp4`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch { toast(t("netErr"), true); }
}
async function loadVideos() {
  const el = $("#histList"); if (!el) return;
  try {
    const d = await api("videos");
    if (!d.ok) return;
    const list = d.videos || [];
    $("#histEmpty").hidden = list.length > 0;
    el.innerHTML = list.map(v => {
      const st = v.state === "done" ? t("histDone") : v.state === "failed" ? t("histFail") : t("histEditing");
      const posted = [v.yt ? "YouTube ✓" : "", v.ig ? "Instagram ✓" : ""].filter(Boolean).join(" · ");
      const date = v.at ? new Date(v.at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "";
      const meta = [esc(v.kind || ""), esc(v.length || ""), date, st].filter(x => x).join(" · ");
      return `<div class="card hist-item"><div class="hist-num">video ${v.n}</div><b>${esc(v.title || v.topic || "")}</b>
        <div class="muted small">${meta}${posted ? " · " + posted : ""}</div>
        <div class="row">${v.has_result ? `<button class="btn secondary" data-watch="${v.job}">${t("histWatch")}</button>` : ""}<button class="btn" data-up="${v.n}">${t("histUpload")}</button></div>
        ${v.yt ? `<div class="muted small"><a href="${v.yt.url}" target="_blank" rel="noopener">${v.yt.url}</a></div>` : ""}${v.ig ? `<div class="muted small"><a href="${v.ig.url}" target="_blank" rel="noopener">${v.ig.url}</a></div>` : ""}</div>`;
    }).join("");
    el.querySelectorAll("[data-watch]").forEach(b => b.onclick = () => watchJob(b.dataset.watch));
    el.querySelectorAll("[data-up]").forEach(b => b.onclick = () => { go("chat"); setTimeout(() => send(`upload video ${b.dataset.up} to YouTube and Instagram`), 300); });
  } catch {}
}

function xhrUpload(path, form, onProg) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest(); x.open("POST", API + "/" + path); x.setRequestHeader("authorization", "Bearer " + S.token);
    x.upload.onprogress = e => e.lengthComputable && onProg(Math.round(e.loaded / e.total * 100));
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch {} if (x.status === 401) { logout(true); return rej(new Error("login")); } res({ status: x.status, ...d }); };
    x.onerror = () => { netState(false); rej(new Error("net")); }; x.send(form);
  });
}
let lastJob = null;
function setJob(kind, when, job) {
  lastJob = job || null;
  const title = kind ? t(kind === "queued" ? "jobQueued" : kind === "run" ? "jobRun" : kind === "done" ? "jobDone" : "jobFail") : t("noJob");
  let sub = kind ? t(job ? (kind === "done" ? "jobDoneSub2" : kind === "fail" ? "jobFailSub2" : "jobRunSub2") : (kind === "done" ? "jobDoneSub" : kind === "fail" ? "jobFailSub" : "jobRunSub")) : t("noJobSub");
  if (job && job.note && kind !== "done") sub = job.note + " · " + sub;
  if (when) sub += " · " + when;
  const cls = "pulse" + (kind === "done" ? " done" : kind === "fail" ? " fail" : kind ? "" : " idle");
  const jc = $("#jobCard"); if (jc) { jc.hidden = !kind; const jd = $("#jobDot"); if (jd) jd.className = cls; const jt = $("#jobTitle"); if (jt) jt.textContent = title; const js = $("#jobSub"); if (js) js.textContent = sub; }
  $("#homeJobDot").className = cls; $("#homeJobTitle").textContent = title; $("#homeJobSub").textContent = sub;
  const db = $("#dlBtn"); if (db) db.hidden = !(job && job.has_result);
}
function showQuota(left, limit, used) {
  S.quota = { left, limit, used };
  $("#homeQuotaNum").textContent = limit === null || limit === undefined ? "∞" : left;
  $("#homeQuotaSub").textContent = S.tok ? t("tokSub", S.tok.weekLeft, S.tok.pool, S.tok.videosWeek, S.tok.weekEnds) : (limit === null || limit === undefined ? t("unlimitedSub") : t("quotaSub", used, limit));
  const eq = $("#editQuota"); if (eq) eq.textContent = t("editsLine", left, limit ?? null);
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
    if (cur === "home" && active) statusTimer = setTimeout(loadStatus, 10000);
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
      ${p.connected ? `<span class="pill ok">✓ ${t("connectedP")}</span>` : p.ready ? `<button class="pill go" data-p="${p.id}" aria-label="${esc(t("connect") + " " + p.name)}">${t("connect")}</button>` : `<span class="pill wait">${t("soon")}</span>`}${p.id === "youtube" ? ` <button class="pill" data-yt="1">${esc(t("openYT"))}</button>` : ""}</div>`).join("");
    $$("#provList [data-p]").forEach(b => b.onclick = () => connectLink(b.dataset.p));
    // v39: the Connect page's YouTube row opens YouTube (app on Android,
    // browser otherwise) — previously it had no way to open YouTube at all.
    $$("#provList [data-yt]").forEach(b => b.onclick = () => { openUrl(ytAppUrl()); });
    const g = d.providers.find(p => p.id === "google");
    if (g) { $("#gWho").textContent = g.connected ? (g.who || t("connectedP")) : t("googleSub"); $("#gBtn").hidden = !!g.connected || !g.ready; }
  } catch {}
}
$("#gBtn").onclick = () => connectLink("google");
$("#loginGoogleBtn") && ($("#loginGoogleBtn").onclick = async () => { const r = await api("auth/google", { method: "POST", json: {} }).catch(() => ({})); if (r.ok && r.url) location.href = r.url; else toast(r.error || t("netErr")); });

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
    const s = keyState[id] || {};
    // R48: "Waiting on you" appears ONLY on the step paused for the user's
    // one tap (email-link tap / SMS code) — never for a key paste or any
    // other step. setupPause is set by the mini-box from setup/status.
    const waiting = setupPause && setupPause.id === id && !(s.set && s.ok);
    const st = s.set ? (s.ok ? t("stepOk", s.who) : t("stepFail")) : waiting ? t("stepWaiting") : t("stepNot");
    return `<li class="step${s.set && s.ok ? " done" : ""}${waiting ? " waiting" : ""}" id="st-${id}"><div class="step-h"><b>${esc(k.name)}</b><span class="pill wait">${esc(st)}</span></div>
      <p class="muted small">${esc(t("d_" + id))}${k.soon ? " " + esc(t("oauthSoon")) : ""}</p>
      <p class="muted small">${esc(t("stepYouDo"))}</p>
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
  renderAutoLog();
}
$("#consent").onchange = e => { S.consent = e.target.checked; store.set("consent", S.consent); syncOneTapBtn(); };
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

/* ---------- R48 login-time setup prompt ----------
   After login, ask the Worker whether setup is actually needed:
   GET setup/status -> {needsSetup, state, steps[]} (v38 Worker shape).
   Only then show the one-allow prompt — never on every login, never once
   setup is done. Allow -> setup/start + the chat mini-box with live
   per-step progress. Decline -> limited mode (chat still works with the
   shared brain if available); the Setup screen (bottom of the drawer) can
   start it later. The prompt comes back only when chat itself fails while
   setup is still needed (send() calls checkSetupPrompt(true)) — never a
   dead-end, never a nag. */
let setupPromptShown = false;
async function checkSetupPrompt(force) {
  if (setupPromptShown || !S.token) return false;
  let d = null;
  try { d = await api("setup/status"); } catch { return false; }
  if (!d || !d.ok) return false;
  if (Array.isArray(d.autoLog)) { lastAutoLog = d.autoLog; renderAutoLog(); }
  // v38 shape: needsSetup + steps[]. Pre-v38 shape has no needsSetup — derive
  // it from {active, finished, keys} (see setupNeedsFrom).
  const needs = d.needsSetup ?? setupNeedsFrom(d);
  if (!needs) return false;
  if (!force && store.get("setupDeclined", false)) return false;
  setupPromptShown = true;
  sheet(t("setupAsk"), [
    { label: t("setupAllow"), primary: true, fn: () => { store.del("setupDeclined"); startOneTapSetup(); } },
    { label: t("later"), fn: () => { store.set("setupDeclined", true); setupPromptShown = false; toast(t("gsDeclined")); } },
  ]);
  return true;
}
/* Pre-v38 setup/status shape {active, finished, keys}: setup is needed when
   no setup run is active, no finished "done" is recorded, and no provider
   key is saved yet. */
function setupNeedsFrom(d) {
  if (d.active) return false;
  if (d.finished && d.finished.state === "done") return false;
  const keys = d.keys || {};
  return !["groq", "openrouter", "gemini"].every(id => keys[id]);
}

/* ---------- plan ---------- */
async function loadPlan() { try { const d = await api("plan"); if (d.ok) { S.plan = d.plan; S.tok = d.tok || null; $("#planNow").textContent = t("planNow", d.plan, d.edits_used, d.edits_limit); showQuota(d.edits_left, d.edits_limit, d.edits_used); renderPlans(d); loadReferral(); if (cur === "profile") renderProfile(); } } catch {} }
async function loadReferral() { try { const d = await api("referral/me"); if (d.ok) { $("#refCode").textContent = d.code; $("#refStatus").textContent = t("inviteStatus", d.invites, d.earned); } } catch {} }
/* v37: voice assistant is INCLUDED in every plan (Ajju) — the separate
   Rs.49/mo add-on line is gone. Each plan card shows the included line from
   the plan's own voice flag (Worker sets voice:true on every plan); a plan
   that explicitly excludes voice shows no line rather than an add-on. */
function renderPlans(d) { const el = $("#planList"); if (!el || !d.plans) return; el.innerHTML = Object.entries(d.plans).map(([id, p]) => `<div class="row"><div><b>${esc(p.name)}</b> <span class="muted small">₹${p.monthly}/mo · ${fmtTok(p.grant)} tokens</span></div>${id === d.plan ? `<span class="pill ok">✓</span>` : ""}</div>${p.voice !== false ? `<p class="muted small">✓ ${esc(t("voiceIncluded"))}</p>` : ""}`).join(""); }

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
$("#setBlind").onchange = e => { S.blind = e.target.checked; store.set("blind", S.blind); applyBlind(); };
function applyBlind() { document.body.classList.toggle("blind", !!S.blind); if (S.blind) { S.vf = true; S.voice = true; store.set("vf", true); store.set("voice", true); $("#setVoice").checked = true; $("#setVF").checked = true; speak(t("blindHello")); } }
$("#refCopy").onclick = async () => { const c = $("#refCode").textContent; if (!c) return; try { await navigator.clipboard.writeText(`https://divya-app.n8n00101.workers.dev/?ref=${c}`); toast(t("copy") + " ✓"); } catch { toast(c); } };
$("#refRedeemBtn").onclick = async () => { const code = $("#refInput").value.trim().toUpperCase(); if (!code) return; const d = await api("referral/redeem", { method: "POST", json: { code } }).catch(() => ({})); $("#refStatus").textContent = d.ok ? `✓ +${(d.reward || 0).toLocaleString("en-IN")} tokens` : (d.error || t("netErr")); if (d.ok) loadPlan(); };
$("#logout").onclick = () => logout(false);
$("#delDataBtn") && ($("#delDataBtn").onclick = () => sheet(t("delDataConfirm"), [{ label: t("cancel") }, { label: t("delData"), primary: true, fn: async () => { const d = await api("account/delete-data", { method: "POST", json: {} }).catch(() => ({})); if (d.ok) { toast(t("delDataDone")); logout(false); } else toast(d.error || t("netErr")); } }]));
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);

/* ---------- floating mini-chat bubble (Phase 1: inside Divya) ---------- */
/* R27: small draggable button (default bottom-right, ABOVE the chat composer), tap opens a
   bottom sheet that never covers the main chat input bar (sheet docks above it, composer
   z-index:70 always wins taps). X closes back to the small button. Position persists. */
function bubbleLog(who, text, buttons) {
  const el = $("#bubbleLog"); if (!el) return;
  const d = document.createElement("div"); d.className = who; d.textContent = (who === "me" ? "Nuvvu: " : "Divya: ") + text; el.appendChild(d);
  if (buttons && buttons.length) {
    const row = document.createElement("div"); row.className = "act";
    buttons.forEach(b => {
      const a = document.createElement(b.href ? "a" : "button"); a.className = "act-btn" + (b.alt ? " alt" : ""); a.textContent = b.label;
      if (b.href) { a.href = b.href; a.target = "_blank"; a.rel = "noopener"; } else if (b.fn) a.onclick = b.fn;
      row.appendChild(a);
    });
    el.appendChild(row);
  }
  el.scrollTop = el.scrollHeight;
}
function bubbleOpen() { const b = $("#bubble"), p = $("#bubblePanel"); b.hidden = false; p.hidden = false; $("#bubbleBtn").hidden = true; $("#bubbleText").focus(); }
function bubbleClose() { $("#bubblePanel").hidden = true; $("#bubbleBtn").hidden = false; }
async function bubbleSend() {
  const inp = $("#bubbleText"); const text = inp.value.trim(); if (!text) return; inp.value = ""; bubbleLog("me", text);
  try {
    // R28: same structured path as the main chat (assist) — never the free-form brain,
    // which invented "Youtube opened." with no action behind it.
    const d = await assist(text);
    const reply = d.reply || d.error || "";
    const p = await runAction(d.action, true);
    bubbleLog("divya", reply + (p.say ? "\n" + p.say : ""), p.buttons);
    if (S.vf || S.blind) speak(reply + (p.say ? " " + p.say : ""));
  } catch { bubbleLog("divya", t("netErr")); }
}
$("#bubbleSend").onclick = bubbleSend;
$("#bubbleText").addEventListener("keydown", e => { if (e.key === "Enter") bubbleSend(); });
$("#bubbleClose").onclick = bubbleClose;
/* Draggable bubble: pointer drag on the round button (closed) or the sheet header (open).
   Tap (moved < 7px) still opens/closes; a real drag moves the bubble and saves the spot. */
(function () {
  const box = $("#bubble"), btn = $("#bubbleBtn"), head = document.querySelector(".bubble-head");
  if (!box || !btn) return;
  // R31: clamp on restore/drag/resize/rotation — the button must stay FULLY
  // visible and ABOVE the tabbar/composer (140px zone at the bottom).
  // v24: the old maxY (innerHeight-40) let the button slide under the tabbar,
  // where it was invisible and untappable until a reload.
  function clampPos(x, y) {
    const w = box.offsetWidth || 56, h = box.offsetHeight || 56;
    const minX = 8, maxX = Math.max(minX, innerWidth - w - 8);
    const minY = 8, maxY = Math.max(minY, innerHeight - h - 140);
    return { x: Math.max(minX, Math.min(x, maxX)), y: Math.max(minY, Math.min(y, maxY)) };
  }
  function applyPos(x, y) { const p = clampPos(x, y); box.style.left = p.x + "px"; box.style.top = p.y + "px"; box.style.right = "auto"; box.style.bottom = "auto"; return p; }
  const saved = store.get("bubblePos", null);
  if (saved && isFinite(saved.x) && isFinite(saved.y)) applyPos(saved.x, saved.y);
  const reClamp = () => { const r = box.getBoundingClientRect(); const p = clampPos(r.left, r.top); if (Math.round(r.left) !== p.x || Math.round(r.top) !== p.y) { applyPos(p.x, p.y); store.set("bubblePos", { x: p.x, y: p.y }); } };
  addEventListener("resize", reClamp);
  addEventListener("orientationchange", () => setTimeout(reClamp, 300));
  let drag = null, suppressClickUntil = 0;
  function onDown(e) {
    if (e.button !== undefined && e.button !== 0) return;
    const r = box.getBoundingClientRect();
    drag = { x0: e.clientX, y0: e.clientY, left: r.left, top: r.top, moved: false, pid: e.pointerId };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch {}
  }
  function onMove(e) {
    if (!drag || e.pointerId !== drag.pid) return;
    const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
    if (!drag.moved && Math.hypot(dx, dy) > 7) { drag.moved = true; box.classList.add("dragging"); }
    if (!drag.moved) return;
    const w = box.offsetWidth, h = box.offsetHeight;
    // R27: the open sheet must never cover the chat composer — clamp its bottom edge
    // to stay 140px above the viewport bottom (tabbar + composer). v24: the closed
    // button gets the same 140px floor — the old 8px floor let it slide under the
    // tabbar, invisible and untappable until a reload.
    const minBottom = 140;
    let left = drag.left + dx, top = drag.top + dy;
    left = Math.max(8, Math.min(left, innerWidth - w - 8));
    top = Math.max(8, Math.min(top, innerHeight - h - minBottom));
    box.style.left = left + "px"; box.style.top = top + "px"; box.style.right = "auto"; box.style.bottom = "auto";
  }
  function onUp(e) {
    if (!drag || e.pointerId !== drag.pid) return;
    const wasDrag = drag.moved; drag = null; box.classList.remove("dragging");
    if (wasDrag) { const r = box.getBoundingClientRect(); store.set("bubblePos", { x: Math.round(r.left), y: Math.round(r.top) }); suppressClickUntil = Date.now() + 300; }
  }
  [btn, head].forEach(el => { if (!el) return; el.addEventListener("pointerdown", onDown); el.addEventListener("pointermove", onMove); el.addEventListener("pointerup", onUp); el.addEventListener("pointercancel", onUp); });
  btn.addEventListener("click", () => { if (Date.now() < suppressClickUntil) return; bubbleOpen(); });
})();

/* ---------- Blind Mode: captcha guide (R48) ----------
   Captchas are part of the one allow: Divya solves them itself (audio
   challenge on-device). This guide appears ONLY when Divya cannot solve one
   alone (an image challenge) — it reads the challenge aloud, and acts only
   after the user's one tap / "cheyu". Never a third-party solving service. */
const captchaGuide = {
  pending: null,
  start(question, answer, onConfirm) {
    this.pending = { answer, onConfirm };
    const msg = `${t("capSolving")}${question ? " " + question : ""}${answer ? " Answer: " + answer + "." : ""} ${t("capNeedTap")}`;
    speak(msg); toast(msg);
    bubbleOpen();
    bubbleLog("divya", `${question} Answer: ${answer}. ${t("capNeedTap")}`);
    const log = $("#bubbleLog");
    const row = document.createElement("div"); row.className = "cap-row";
    row.innerHTML = `<button class="btn primary" id="capYes">✓ Cheyu</button><button class="btn" id="capNo">Kadhu</button>`;
    log.appendChild(row); log.scrollTop = log.scrollHeight;
    $("#capYes").onclick = () => this.confirm();
    $("#capNo").onclick = () => this.decline();
    this.listenYesNo();
  },
  listenYesNo() {
    const SRc = (typeof SR !== "undefined" && SR) || window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SRc) return;
    try {
      const r = new SRc(); r.lang = srLang(); r.interimResults = false; r.maxAlternatives = 1;
      r.onresult = e => { const heard = (e.results[0][0].transcript || "").toLowerCase(); if (/cheyu|avunu|yes|do it|sare/.test(heard)) this.confirm(); else if (/kadhu|no|vadhu|aagu/.test(heard)) this.decline(); };
      r.onerror = () => {}; r.onend = () => {};
      r.start(); setTimeout(() => { try { r.stop(); } catch {} }, 12000);
    } catch {}
  },
  confirm() { const p = this.pending; this.pending = null; if (p?.onConfirm) p.onConfirm(); speak(t("capDone")); toast(t("capDone"), true); },
  decline() { this.pending = null; speak(t("capNo")); toast(t("capNo")); },
};
// One-shot voice question -> answer (used by blind signup + captcha guide).
function askVoice(question) {
  return new Promise(res => {
    speak(question);
    const SRc = (typeof SR !== "undefined" && SR) || window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SRc) return res(null);
    try {
      const r = new SRc(); r.lang = srLang(); r.interimResults = false;
      let done = false;
      r.onresult = e => { if (!done) { done = true; res((e.results[0][0].transcript || "").trim() || null); } };
      r.onerror = () => { if (!done) { done = true; res(null); } };
      r.onend = () => { if (!done) { done = true; res(null); } };
      r.start(); setTimeout(() => { try { r.stop(); } catch {} }, 15000);
    } catch { res(null); }
  });
}
/* ---------- Blind Mode: voice signup (alone, no help) ---------- */
async function blindSignup() {
  const steps = [
    { id: "suName", q: "Nee peru enti?", back: v => `Peru ${v}. Correct aa? "Avunu" ani cheppu.` },
    { id: "suEmail", q: "Email enti?", back: v => `Email ${v}. Correct aa? "Avunu" ani cheppu.` },
    { id: "suPhone", q: "WhatsApp number enti? 10 digits cheppu.", back: v => `Number ${v}. Correct aa? "Avunu" ani cheppu.` },
  ];
  for (const s of steps) {
    const v = await askVoice(s.q);
    if (!v) { speak("Vinaledu. Type cheyyi leda malli cheppu."); continue; }
    const ok = await askVoice(s.back(v));
    if (!/avunu|yes|correct|sare/.test((ok || "").toLowerCase())) { speak("Sare, malli cheppu."); continue; }
    const el = $("#" + s.id); if (el) el.value = s.id === "suPhone" ? v.replace(/\D/g, "").slice(-10) : v;
  }
  speak("Password ni voice lo cheppaku — pakkana unna vallaki vinipisthundhi. Password type cheyyi, tarvatha Create nokku. Nenu guide chestha.");
}
$("#suVoiceBtn").onclick = () => blindSignup();

/* ---------- boot ---------- */
function enter() {
  $("#login").hidden = true; $("#main").hidden = false; $("#bubble").hidden = false; $("#me").textContent = t("loggedIn", whoAmI()); $("#drawerMe").textContent = whoAmI(); renderAcct(); refreshMe();
  loadHistory(); loadConnect(); loadKeys(); warmVoices(); schedule(); cur = "";
  route(); setTimeout(() => $("#screen-title").focus({ preventScroll: true }), 50);
  if (store.get("orcode", "")) { go("setup"); orFinish(); }
  if (S.wake && SR) vaStart();
  setTimeout(() => checkSetupPrompt(), 3000); // R48: login-time setup prompt — only when setup/status says it is needed
}
// OpenRouter PKCE callback lands on /setup?code=...
if (location.pathname.endsWith("/setup") || new URLSearchParams(location.search).has("orcb")) { const c = new URLSearchParams(location.search).get("code"); if (c) store.set("orcode", c); history.replaceState(null, "", BASE + "#/setup"); }
// Google login callback lands on /?gtoken=... — store the session and enter.
const gt = new URLSearchParams(location.search).get("gtoken");
if (gt) { S.token = gt; store.set("token", gt); history.replaceState(null, "", BASE + "#/home"); }
applyTheme(); applyLang(); $("#setVoice").checked = S.voice; $("#setVF").checked = S.vf; $("#setBlind").checked = S.blind; applyBlind(); $("#wakeToggle").checked = S.wake && !!SR; $("#wakeToggle").disabled = !SR; updateBtn(); setJob(null); setVState("idle");
if (S.token) { enter(); netCheck(); } else showLogin();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
/* ---------- app updates: a stale cached shell bit twice (black screen; missing
   templates/voices). The live sw.js file is the source of truth — when it reports
   a newer version than this build, prompt for a refresh; a new service worker
   taking control reloads once automatically (only if a worker was already
   controlling the page, and never mid-send or mid-job). ---------- */
let updShown = false;
function showUpdBanner(v) { if (updShown) return; updShown = true; const b = $("#updBanner"); if (!b) return; $("#updText").textContent = t("updBanner", v); b.hidden = false; }
async function checkUpdate(manual) {
  try {
    const r = await fetch("sw.js", { cache: "no-store" });
    const m = (await r.text()).match(/const V = "([^"]+)"/);
    if (!m) { if (manual) toast(t("netErr"), true); return; }
    if (m[1] !== APP_V) { showUpdBanner(m[1]); navigator.serviceWorker?.getRegistration().then(r => r?.update().catch(() => {})); }
    else if (manual) toast(t("updLatest"));
  } catch { if (manual) toast(t("netErr"), true); }
}
$("#updRefreshBtn") && ($("#updRefreshBtn").onclick = () => location.reload());
$("#updRow") && ($("#updRow").onclick = () => checkUpdate(true));
if ("serviceWorker" in navigator) {
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController) return; // first install — no reload needed
    if (sessionStorage.getItem("updReloaded") === "1") return;
    if (busy || $("#jobCard")?.hidden === false) { checkUpdate(false); return; } // mid-work: banner only, with the real new version
    sessionStorage.setItem("updReloaded", "1");
    location.reload(); // new worker took control — reload once into the new version
  });
}
checkUpdate(false);
setInterval(() => checkUpdate(false), 15 * 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkUpdate(false); });
