# H Kingdom All-Stars - single-file Flask + Socket.IO app
# Run: pip install flask flask-socketio eventlet
# Then: python h_kingdom_allstars.py
# Place a 'Pinky Sprite.png' file inside a directory named 'static' next to this file

from flask import Flask, render_template_string, request, send_file, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, send
import eventlet
import time
import random
import threading
import io
import zipfile
import json

# --- Config ---
WORKER_PASSWORD = 'qwertyO9385HHHkbrox67iop'
TICK_RATE = 0.05  # server tick for bots/match updates

app = Flask(__name__)
app.config['SECRET_KEY'] = 'hkingdomsecret'
socketio = SocketIO(app, cors_allowed_origins='*')

# --- In-memory stores (no DB) ---
USERS = {}  # email -> {email, password, username, xp, friends:set, incoming_requests:set}
SESSIONS = {}  # sid -> email
BATTLEPASS = []  # list of character dicts
GAMES = {}  # game_id -> game state
MATCH_QUEUE = {'solos': [], 'duos': [], 'trios': [], 'squads': [], 'megas': []}

# --- Helpers ---
import uuid

def make_user(email, password, username):
    USERS[email] = {
        'email': email,
        'password': password,
        'username': username,
        'xp': 0,
        'friends': set(),
        'incoming': set()
    }
    return USERS[email]

# default test user
make_user('test@example.com', 'pass', 'testplayer')

# --- Templates ---
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>H Kingdom All-Stars</title>
  <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
  <style>
    body{font-family:Arial;margin:0;background:#111;color:#fff}
    .center{display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column}
    .btn{padding:10px 18px;border-radius:8px;margin:8px;cursor:pointer}
    .blue{background:#2b7cff;color:#fff}
    .green{background:#2ecc71;color:#033}
    .red{background:#ff4d4d;color:#fff}
    .yellow-square{width:96px;height:96px;background:#ffd500;margin:6px;display:inline-block;position:relative}
    .lobby-row{display:flex;align-items:center}
    #pinky{width:84px;height:84px;object-fit:contain}
    #game-canvas{background:#2ecc71;width:800px;height:500px}
    .small{font-size:12px}
  </style>
</head>
<body>
<div id="app" class="center">
  <h1>H Kingdom All-Stars</h1>
  <button class="btn" onclick="installGame()">INSTALL GAME</button>
  <div id="auth"></div>
  <div id="lobby" style="display:none">
    <div class="lobby-row">
      <div class="yellow-square"></div>
      <div class="yellow-square"></div>
      <div class="yellow-square"><img id="pinky" src="/static/Pinky%20Sprite.png" onerror="this.style.display='none'"/></div>
      <div class="yellow-square"></div>
      <div class="yellow-square"></div>
    </div>
    <div style="margin-top:12px">
      <button class="btn blue" onclick="showPlay()">Play</button>
      <button class="btn green" onclick="showFriends()">Friends</button>
      <button class="btn red" onclick="showBattlepass()">Battlepass</button>
    </div>
  </div>
</div>

<script>
const socket = io();
let myEmail=null;

function installGame(){
  window.location.href='/install';
}

// --- Auth UI ---
const authHTML = `
  <div>
    <h3>Sign Up</h3>
    <input id="su_email" placeholder="email"><br>
    <input id="su_user" placeholder="username"><br>
    <input id="su_pass" placeholder="password" type="password"><br>
    <button onclick="signup()">Sign Up</button>
    <hr>
    <h3>Log In</h3>
    <input id="li_email" placeholder="email"><br>
    <input id="li_pass" placeholder="password" type="password"><br>
    <button onclick="login()">Log In</button>
    <button onclick="workerLogin()">Log in as worker</button>
  </div>
`;

document.getElementById('auth').innerHTML = authHTML;

function signup(){
  fetch('/api/signup', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('su_email').value,password:document.getElementById('su_pass').value,username:document.getElementById('su_user').value})}).then(r=>r.json()).then(j=>{if(j.ok){myEmail=j.email;enterLobby()}else alert(j.err)})
}
function login(){
  fetch('/api/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('li_email').value,password:document.getElementById('li_pass').value})}).then(r=>r.json()).then(j=>{if(j.ok){myEmail=j.email;enterLobby()}else alert(j.err)})
}
function workerLogin(){
  const pwd = prompt('Worker password');
  fetch('/api/worker_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pwd})}).then(r=>r.json()).then(j=>{if(j.ok){alert('Worker mode enabled'); localStorage.setItem('worker','1'); enterLobby()} else alert('Bad worker password')})
}

function enterLobby(){
  document.getElementById('auth').style.display='none';
  document.getElementById('lobby').style.display='block';
}

// --- Play / Friends / Battlepass ---
function showFriends(){
  const html = `
    <h3>Friends</h3>
    <input id="search_friend" placeholder="search username">
    <button onclick="searchFriend()">Search</button>
    <div id="friend_results"></div>
    <h4>Requests</h4>
    <div id="friend_requests"></div>
    <button onclick="closePanel()">Back</button>
  `;
  showPanel(html);
  refreshRequests();
}
function refreshRequests(){fetch('/api/requests').then(r=>r.json()).then(j=>{const el=document.getElementById('friend_requests');el.innerHTML='';j.requests.forEach(req=>{const d=document.createElement('div');d.innerHTML=`${req}<button onclick="respondRequest('${req}',true)">Accept</button><button onclick="respondRequest('${req}',false)">Decline</button>`;el.appendChild(d)})})}
function respondRequest(from,accept){fetch('/api/respond_request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from,accept})}).then(r=>r.json()).then(()=>refreshRequests())}
function searchFriend(){const q=document.getElementById('search_friend').value;fetch('/api/search_user?q='+encodeURIComponent(q)).then(r=>r.json()).then(j=>{const el=document.getElementById('friend_results');el.innerHTML='';j.results.forEach(u=>{const d=document.createElement('div');d.innerHTML=`${u.username} <button onclick="sendReq('${u.email}')">Friend Request</button>`;el.appendChild(d)})})}
function sendReq(email){fetch('/api/send_request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})}).then(r=>r.json()).then(j=>alert(j.msg))}

function showPlay(){
  const html = `
    <h3>Play</h3>
    <div>Pick mode:<br>
    <button onclick="startMatch('solos')">Solos</button>
    <button onclick="startMatch('duos')">Duos</button>
    <button onclick="startMatch('trios')">Trios</button>
    <button onclick="startMatch('squads')">Squads</button>
    <button onclick="startMatch('megas')">Megas</button>
    </div>
    <button onclick="closePanel()">Back</button>
  `;
  showPanel(html);
}

function showBattlepass(){
  fetch('/api/battlepass').then(r=>r.json()).then(j=>{
    let html='<h3>Battlepass</h3>';
    if(localStorage.getItem('worker')) html+='<button onclick="openWorkerEditor()">Worker: Add Character</button>';
    html+='<div id="bp_list">';
    j.forEach(c=>{html+=`<div>${c.name} - cost: ${c.xp_cost} XP <button onclick="buy('${c.name}')">Buy</button></div>`});
    html+='</div><button onclick="closePanel()">Back</button>';
    showPanel(html);
  })
}
function openWorkerEditor(){
  const html = `
    <h3>Add Character</h3>
    <input id="ch_name" placeholder="name"><br>
    <input id="ch_xp" placeholder="xp cost"><br>
    <input id="ch_size" placeholder="size (int)"><br>
    <input id="ch_speed" placeholder="speed (float)"><br>
    <input id="ch_hp" placeholder="hp"><br>
    <input id="ch_img" placeholder="image filename in static/ (optional)"><br>
    <h4>Attack move</h4>
    <input id="atk_name" placeholder="attack name"><br>
    <input id="atk_radius" placeholder="radius"><br>
    <input id="atk_damage" placeholder="damage"><br>
    <input id="atk_key" placeholder="key"><br>
    <input id="atk_cool" placeholder="cooldown seconds"><br>
    <button onclick="addCharacter()">Add</button>
    <button onclick="closePanel()">Back</button>
  `;
  showPanel(html);
}
function addCharacter(){
  const data = {
    name:document.getElementById('ch_name').value,
    xp_cost:parseInt(document.getElementById('ch_xp').value||0),
    size:parseInt(document.getElementById('ch_size').value||32),
    speed:parseFloat(document.getElementById('ch_speed').value||1.0),
    hp:parseInt(document.getElementById('ch_hp').value||100),
    img:document.getElementById('ch_img').value||'',
    attack:{name:document.getElementById('atk_name').value, radius:parseFloat(document.getElementById('atk_radius').value||0), damage:parseInt(document.getElementById('atk_damage').value||0), key:document.getElementById('atk_key').value, cooldown:parseFloat(document.getElementById('atk_cool').value||0)}
  };
  fetch('/api/add_character',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(j=>{alert(j.msg);showBattlepass()})
}

function buy(name){fetch('/api/buy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}).then(r=>r.json()).then(j=>alert(j.msg))}

function startMatch(mode){
  fetch('/api/has_friends').then(r=>r.json()).then(j=>{
    if(mode!=='solos' && j.count===0){alert('not available'); return;} // no friends
    if(mode!=='solos'){
      // pick friends
      const f = prompt('Pick friend username to invite (comma separated indices from list):\n'+j.list.map((x,i)=>i+':'+x).join('\n'));
      // simple: send invites
      if(f!==null){
        const idxs = f.split(',').map(x=>parseInt(x.trim())).filter(x=>!isNaN(x));
        const chosen = idxs.map(i=>j.list[i]).filter(Boolean);
        fetch('/api/start_match',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,invites:chosen})}).then(r=>r.json()).then(res=>{alert(res.msg)});
      }
    } else {
      fetch('/api/start_match',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,invites:[]})}).then(r=>r.json()).then(res=>{alert(res.msg)});
    }
  })
}

// generic panel helper
function showPanel(html){
  const w = window.open('','panel','width=600,height=600,resizable=yes');
  w.document.body.style.background='#222';
  w.document.body.style.color='#fff';
  w.document.body.innerHTML = html;
}
function closePanel(){window.open('','panel').close();}

// --- Realtime Socket Handling for invites and games ---
socket.on('connect', ()=>{console.log('socket connected')});

socket.on('invite', data => { if(confirm(`Do you want to join ${data.from}'s game?`)){ socket.emit('invite_response',{game_id:data.game_id,accept:true}) } else socket.emit('invite_response',{game_id:data.game_id,accept:false}) });

// Move to game page
socket.on('start_game', data => {
  // open game window
  const w = window.open('','gamewin','width=900,height=700,resizable=yes');
  w.document.title='H Kingdom - match';
  const html = `
    <canvas id='gc' width=900 height=600></canvas>
    <div id='hud'></div>
    <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
    <script>
    const s = io();
    const canvas = document.getElementById('gc'); const ctx = canvas.getContext('2d');
    let me=null;
    const keys = {};
    window.addEventListener('keydown', e=>{keys[e.key.toLowerCase()]=true;s.emit('key',{k:e.key});});
    window.addEventListener('keyup', e=>{keys[e.key.toLowerCase()]=false;});
    s.on('connect', ()=>{});
    s.on('state', st => {
      // draw
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle='#2ecc71'; ctx.fillRect(0,0,canvas.width,canvas.height);
      for(const p of st.players){
        const img = new Image(); img.src = p.img || '/static/Pinky%20Sprite.png';
        const x = p.x/100*canvas.width; const y = p.y/100*canvas.height;
        ctx.save();
        if(p.is_friend) ctx.globalAlpha=0.6;
        ctx.drawImage(img, x-p.size/2, y-p.size/2, p.size, p.size);
        ctx.restore();
        // hp bar
        ctx.fillStyle='black'; ctx.fillRect(x-p.size/2, y-p.size/2-6, p.size,4);
        ctx.fillStyle='red'; ctx.fillRect(x-p.size/2, y-p.size/2-6, p.size*(p.hp/p.maxhp),4);
      }
      // hud
      document.getElementById('hud').innerText = 'Players:'+st.players.length;
    });
    s.emit('join_game',{game_id:'${data.game_id}'});
    </script>
  `;
  w.document.body.innerHTML = html;
});

</script>
</body>
</html>
"""

# --- Flask routes ---
@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/install')
def install():
    # create a zip containing a tiny launcher and README
    mem = io.BytesIO()
    z = zipfile.ZipFile(mem, 'w')
    z.writestr('README.txt', 'Unzip and run run_game.bat (Windows) or run_game.sh (Linux/Mac)')
    z.writestr('run_game.bat', 'python h_kingdom_allstars.py')
    z.writestr('run_game.sh', '#!/bin/sh\npython3 h_kingdom_allstars.py')
    z.close()
    mem.seek(0)
    return send_file(mem, download_name='H_Kingdom_AllStars_installer.zip', as_attachment=True)

# --- API endpoints for auth / friends / battlepass ---
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.get_json()
    email = data.get('email')
    pwd = data.get('password')
    username = data.get('username')
    if not email or not pwd or not username:
        return jsonify({'ok':False,'err':'missing fields'})
    if email in USERS:
        return jsonify({'ok':False,'err':'exists'})
    make_user(email,pwd,username)
    return jsonify({'ok':True,'email':email})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    pwd = data.get('password')
    u = USERS.get(email)
    if not u or u['password']!=pwd:
        return jsonify({'ok':False,'err':'bad'})
    return jsonify({'ok':True,'email':email})

@app.route('/api/worker_login', methods=['POST'])
def api_worker_login():
    data = request.get_json()
    pwd = data.get('pwd')
    if pwd==WORKER_PASSWORD:
        return jsonify({'ok':True})
    return jsonify({'ok':False})

@app.route('/api/search_user')
def api_search():
    q = request.args.get('q','').lower()
    res = []
    for e,u in USERS.items():
        if q in u['username'].lower(): res.append({'email':e,'username':u['username']})
    return jsonify({'results':res})

@app.route('/api/send_request', methods=['POST'])
def api_send_request():
    data = request.get_json()
    target = data.get('email')
    # simulate logged-in via header referer: in real app you'd use sessions
    sender = request.remote_addr + ':' + request.headers.get('User-Agent','')[:30]
    # for simplicity, assume request includes a header 'X-User-Email' in client fetch - but our client does not
    # Instead we just pick first user (test) for prototype
    # NOTE: This is a prototype: real auth required
    if target in USERS:
        USERS[target]['incoming'].add('testplayer')
        return jsonify({'msg':'request sent'})
    return jsonify({'msg':'no such user'})

@app.route('/api/requests')
def api_requests():
    # prototype: return test user's incoming
    reqs = list(USERS['test@example.com']['incoming'])
    return jsonify({'requests':reqs})

@app.route('/api/respond_request', methods=['POST'])
def api_respond_request():
    data = request.get_json()
    frm = data.get('from')
    accept = data.get('accept')
    # prototype behaviour
    if frm in USERS:
        USERS['test@example.com']['incoming'].discard(frm)
        if accept:
            USERS['test@example.com']['friends'].add(frm)
            USERS[frm]['friends'].add('test@example.com')
        return jsonify({'ok':True})
    return jsonify({'ok':False})

@app.route('/api/has_friends')
def api_has_friends():
    # return prototype: list of friends
    friends = [USERS['test@example.com']['username']]
    return jsonify({'count':len(friends),'list':friends})

@app.route('/api/start_match', methods=['POST'])
def api_start_match():
    data = request.get_json()
    mode = data.get('mode')
    invites = data.get('invites',[])
    gid = str(uuid.uuid4())
    # create game state
    GAMES[gid] = create_game(gid, mode)
    # for invites: emit socket events in real app
    return jsonify({'msg':'match started (prototype)','game_id':gid})

@app.route('/api/battlepass')
def api_battlepass():
    return jsonify(BATTLEPASS)

@app.route('/api/add_character', methods=['POST'])
def api_add_character():
    data = request.get_json()
    BATTLEPASS.append(data)
    return jsonify({'msg':'added'})

@app.route('/api/buy', methods=['POST'])
def api_buy():
    data = request.get_json()
    name = data.get('name')
    # prototype: always succeed
    return jsonify({'msg':'bought (prototype)'})

# --- Game logic ---

def create_game(gid, mode):
    # simple game with multiple players and bots
    state = {
        'id':gid,
        'mode':mode,
        'players':[], # each: {id, x,y, hp, maxhp, size, speed, is_bot, username, img}
        'started': True,
        'created': time.time()
    }
    # fill with bots to simulate a match
    for i in range(20):
        state['players'].append({'id':f'bot{i}','x':random.uniform(0,100),'y':random.uniform(0,100),'hp':175,'maxhp':175,'size':24,'speed':1.2,'is_bot':True,'username':f'Bot{i}','img':''})
    # add a sample player
    state['players'].append({'id':'you','x':50,'y':50,'hp':175,'maxhp':175,'size':32,'speed':1.0,'is_bot':False,'username':'testplayer','img':''})
    return state

# server loop to tick bots

def server_tick():
    while True:
        for gid,g in list(GAMES.items()):
            if not g['started']: continue
            # move bots randomly
            for p in g['players']:
                if p['is_bot']:
                    p['x'] = (p['x'] + random.uniform(-1,1)*p['speed'])
                    p['y'] = (p['y'] + random.uniform(-1,1)*p['speed'])
                    p['x'] = max(0,min(100,p['x'])); p['y'] = max(0,min(100,p['y']))
            # simple win condition
            alive = [p for p in g['players'] if p['hp']>0 and not p.get('is_spectator')]
            teams = 1
            if len(alive)<=1:
                # end game
                g['started']=False
        time.sleep(TICK_RATE)

threading.Thread(target=server_tick,daemon=True).start()

# --- SocketIO events (prototype) ---
@socketio.on('join_game')
def on_join_game(data):
    gid = data.get('game_id')
    # send state once
    g = GAMES.get(gid)
    if not g:
        emit('state', {'players':[]})
        return
    # build player view list
    plist = []
    for p in g['players']:
        plist.append({'id':p['id'],'x':p['x'],'y':p['y'],'hp':p['hp'],'maxhp':p['maxhp'],'size':p['size'],'img':p.get('img'),'is_friend':False})
    emit('state', {'players':plist})

# --- Run ---
if __name__=='__main__':
    print('H Kingdom All-Stars server starting...')
    socketio.run(app, host='0.0.0.0', port=5000)
