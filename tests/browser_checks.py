"""Browser regressions: python3 tests/browser_checks.py (requires Playwright + Chromium)."""
import functools
import http.server
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(root)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.assertEqual(self.page.goto(self.url).status, 200)

    def tearDown(self):
        errors = self.errors[:]
        self.page.close()
        self.assertEqual(errors, [], 'JavaScript errors')

    def practice(self, decks=1, count=26, group=2):
        self.page.evaluate('''([decks,count,group])=>{
            resetPractice();switchTab('practice');
            document.getElementById('pracDecks').value=decks;
            document.getElementById('pracCardCount').value=count;
            document.getElementById('pracGroupSize').value=group;
            onDecksChange();startPractice();
        }''', [str(decks), str(count), str(group)])

    def body_focus(self):
        self.page.evaluate('document.activeElement.blur()')

    def controlled_clocks(self):
        self.page.evaluate('''window.wallNow=10000;window.activeNow=10000;
            Date.now=()=>wallNow;performance.now=()=>activeNow;
            window.ticks=new Map();window.tickId=0;
            window.setInterval=fn=>{const id=++tickId;ticks.set(id,fn);return id};
            window.clearInterval=id=>ticks.delete(id);''')

    def advance_clocks(self, ms):
        self.page.evaluate('ms=>{wallNow+=ms;activeNow+=ms}',ms)

    def test_association_all_modes_and_correct_answers(self):
        self.assertEqual(self.page.evaluate('DATA.length'), 52)
        self.assertEqual(self.page.evaluate('new Set(DATA.map(cardKey)).size'), 52)
        for fmt in ['input', 'show']:
            for unit in ['one', 'two', 'mix']:
                for direction in ['toAssoc', 'toCard', 'mix']:
                    with self.subTest(fmt=fmt, unit=unit, direction=direction):
                        summary = self.page.evaluate('''([fmt,unit,dir])=>{
                            Object.assign(assoc,{fmt,unit,dir});restart();
                            const count=aItems.length;
                            const cards=aItems.flatMap(it=>it.cards).length;
                            while(index<aItems.length){
                                if(fmt==='show'){revealOrNext();revealOrNext();}
                                else {
                                    const it=aItems[index];
                                    const a=it.dir==='toAssoc'?it.cards[0].main:cardCode(it.cards[0]);
                                    const b=it.cards.length===2?(it.dir==='toAssoc'?actionOf(it.cards[1])[0]:cardCode(it.cards[1])):'';
                                    document.getElementById('answerInput').value=a;
                                    document.getElementById('answerInput2').value=b;
                                    submitAndNext();
                                }
                            }
                            return {count,cards,answered:answers.length,wrong:answers.filter(a=>a.correct===false).map(a=>cardCode(a.item.cards[1]||a.item.cards[0]))};
                        }''', [fmt, unit, direction])
                        self.assertEqual(summary['cards'], 52)
                        self.assertEqual(summary['count'], summary['answered'])
                        self.assertEqual(summary['wrong'], [])
                        self.assertTrue(self.page.locator('#resultsArea').is_visible())

    def test_association_input_keyboard_and_escaping(self):
        self.page.evaluate("Object.assign(assoc,{fmt:'input',unit:'two',dir:'toAssoc'});restart()")
        a, b = self.page.evaluate('[aItems[0].cards[0].main,actionOf(aItems[0].cards[1])[0]]')
        self.page.locator('#answerInput').fill(a)
        self.page.locator('#answerInput').press('Enter')
        self.assertTrue(self.page.locator('#answerInput2').evaluate('(el)=>el===document.activeElement'))
        self.page.locator('#answerInput2').fill(b)
        self.page.locator('#answerInput2').press('Enter')
        self.assertEqual(self.page.evaluate('answers.length'), 1)
        self.page.locator('#answerInput').fill('<img src=x onerror="window.bad=true">')
        self.page.locator('#checkNowBtn').click()
        self.assertFalse(self.page.evaluate('!!window.bad'))
        self.assertEqual(self.page.locator('#wrongGrid img').count(), 0)

    def test_card_input_notation(self):
        failures = self.page.evaluate('''()=>DATA.flatMap(c=>[cardCode(c),`${c.suit} ${c.rank}`].filter(v=>!matchCard(c,v)))''')
        self.assertEqual(failures, [])
        self.assertFalse(self.page.evaluate("matchCard(DATA[0],'туз')"))
        self.assertFalse(self.page.evaluate("matchCard(DATA[0],'пики 99')"))

    def test_practice_matrix_and_full_scoring(self):
        for decks,count,group in [(0,1,1),(0,7,3),(0,51,5),(1,52,1),(1,52,2),(1,52,4),(2,104,3),(5,260,5)]:
            with self.subTest(decks=decks,count=count,group=group):
                self.practice(decks,count,group)
                self.assertEqual(self.page.evaluate('prac.sequence.length'), count)
                self.assertEqual(self.page.evaluate('prac.groups.flat().length'), count)
                self.page.evaluate('skipToRecall()')
                self.page.evaluate('''()=>{
                    if(prac.usePerDeck) for(let d=0;d<prac.decks;d++){
                        switchDeckTab(d);prac.perDeck[d].seq.forEach((c,i)=>placeCardInSlot(cardKey(c),i));
                    } else prac.sequence.forEach((c,i)=>placeCardInSlot(cardKey(c),i));
                    finishRecall();
                }''')
                self.assertEqual(self.page.locator('.prac-result-item.correct').count(),count)
                self.assertIn(f'{count} / {count} (100%)',self.page.locator('#pracStatsBox').inner_text())
                self.assertTrue(self.page.locator('#pracResults').is_visible())

    def test_slot_replacement_removal_and_conservation(self):
        self.practice();self.page.evaluate('skipToRecall()')
        self.page.evaluate('''()=>{placeCardInSlot(cardKey(prac.poolCards[0]),0);placeCardInSlot(cardKey(prac.poolCards[1]),0);}''')
        self.assertEqual(self.page.evaluate('prac.placedCount'),1)
        self.assertEqual(self.page.evaluate('prac.poolCounts[cardKey(prac.poolCards[0])]'),1)
        self.assertIn('2',self.page.locator('.slot').first.get_attribute('aria-label'))
        self.page.evaluate('onSlotInteract(0)')
        self.assertEqual(self.page.evaluate('prac.placedCount'),0)
        self.assertEqual(self.page.evaluate('Object.values(prac.poolCounts).reduce((a,b)=>a+b,0)'),52)
        self.assertEqual(self.page.locator('.pool-item').count(),52)

    def test_hidden_practice_does_not_capture_keys(self):
        self.practice();self.page.evaluate("skipToRecall();switchTab('catalog')");self.body_focus()
        self.page.keyboard.press('f')
        self.assertFalse(self.page.evaluate("document.getElementById('pracResults').classList.contains('active')"))
        self.assertIsNotNone(self.page.evaluate('prac.recallStartTs'))

    def test_backspace_removes_instead_of_replacing(self):
        self.practice();self.page.evaluate('''skipToRecall();placeCardInSlot(cardKey(prac.poolCards[0]),0);selectedKey=cardKey(prac.poolCards[1]);updatePoolSelectionUI()''');self.body_focus()
        self.page.keyboard.press('Backspace')
        self.assertIsNone(self.page.evaluate('prac.slots[0]'))
        self.assertEqual(self.page.evaluate('prac.placedCount'),0)

    def test_keyboard_selection_scrolls_into_view(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.practice();self.page.evaluate('skipToRecall()');self.body_focus()
        self.page.keyboard.press('ArrowLeft')
        self.assertEqual(self.page.evaluate('fanFocusIndex'),51)
        self.assertGreater(self.page.evaluate('document.getElementById("poolGrid").scrollLeft'),100)

    def test_result_grid_after_multideck_restart(self):
        self.practice(2,104);self.page.evaluate('skipToRecall();finishRecall()')
        self.practice();self.page.evaluate('skipToRecall();finishRecall()')
        self.assertTrue(self.page.locator('#pracResultGrid').evaluate("el=>el.classList.contains('prac-result-grid')"))

    def test_timer_expiry_and_reset(self):
        self.page.evaluate('''window.testNow=10000;performance.now=()=>window.testNow;Date.now=()=>window.testNow;window.ticks=new Map();window.tickId=0;window.setInterval=fn=>{const id=++tickId;ticks.set(id,fn);return id};window.clearInterval=id=>ticks.delete(id)''')
        self.practice();self.page.evaluate('testNow+=35000;skipToRecall()')
        self.assertEqual(self.page.evaluate('prac.memoElapsed'),35)
        self.page.evaluate('testNow+=34000;finishRecall();finishRecall()')
        self.assertEqual(self.page.evaluate('prac.recallElapsed'),34)
        self.practice();self.page.evaluate('prac.memoLimitSec=2;testNow+=2500;ticks.get(prac.memoTimerId)()')
        self.assertEqual(self.page.evaluate('prac.memoElapsed'),2)
        self.page.evaluate('prac.recallLimitSec=2;testNow+=2500;ticks.get(prac.recallTimerId)()')
        self.assertEqual(self.page.evaluate('prac.recallElapsed'),2)
        self.page.evaluate('resetPractice()');self.assertEqual(self.page.evaluate('ticks.size'),0)

    def test_practice_space_does_not_stop_time(self):
        self.page.evaluate('window.testNow=10000;Date.now=()=>testNow;performance.now=()=>testNow')
        self.practice()
        self.assertEqual(self.page.get_by_role('button',name='Пауза',exact=True).count(),0)
        for phase in ['memo','recall']:
            with self.subTest(phase=phase):
                self.body_focus()
                self.page.evaluate('testNow+=5000')
                self.page.keyboard.down('Space')
                self.page.keyboard.down('Space')
                self.page.keyboard.up('Space')
                self.page.evaluate('testNow+=30000')
                self.page.evaluate('skipToRecall()' if phase=='memo' else 'finishRecall()')
                self.assertEqual(self.page.evaluate(f'prac.{phase}Elapsed'),35)

    def test_timers_include_background_time_without_callbacks(self):
        self.page.evaluate('''window.wallNow=10000;window.activeNow=10000;
            Date.now=()=>wallNow;performance.now=()=>activeNow;
            window.setInterval=()=>1;window.clearInterval=()=>{};''')
        self.page.evaluate("document.getElementById('pracMemoMin').value='0';document.getElementById('pracMemoSec').value='0'")
        self.practice(1,52)
        self.page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});testHidden=true;document.dispatchEvent(new Event('visibilitychange'));switchTab('catalog');wallNow+=540000;activeNow+=5000;testHidden=false;document.dispatchEvent(new Event('visibilitychange'));switchTab('practice');skipToRecall()")
        self.assertEqual(self.page.evaluate('prac.memoElapsed'),540)
        self.page.evaluate("testHidden=true;document.dispatchEvent(new Event('visibilitychange'));wallNow+=495000;activeNow+=5000;testHidden=false;document.dispatchEvent(new Event('visibilitychange'));finishRecall()")
        stats=self.page.locator('#pracStatsBox').inner_text()
        self.assertIn('Время запоминания: 9 мин 0 сек',stats)
        self.assertIn('Время вспоминания: 8 мин 15 сек',stats)

    def test_recall_rejects_placement_at_deadline_without_timer_tick(self):
        for elapsed in [2000,2001,60000]:
            with self.subTest(elapsed=elapsed):
                self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2')
                self.advance_clocks(elapsed)
                self.page.evaluate('placeCardInSlot(cardKey(prac.sequence[0]),0)')
                self.assertEqual(self.page.evaluate('prac.placedCount'),0)
                self.assertTrue(self.page.locator('#pracResults').is_visible())
                self.assertEqual(self.page.evaluate('prac.recallElapsed'),2)

    def test_recall_rejects_removal_after_deadline(self):
        self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2;placeCardInSlot(cardKey(prac.sequence[0]),0)')
        self.advance_clocks(2100)
        self.page.evaluate('onSlotInteract(0)')
        self.assertEqual(self.page.locator('.prac-result-item.correct').count(),1)
        self.assertEqual(self.page.evaluate('prac.placedCount'),1)

    def test_recall_boundary_preserves_last_valid_answer(self):
        self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2')
        self.advance_clocks(1999)
        self.page.evaluate('placeCardInSlot(cardKey(prac.sequence[0]),0)')
        self.advance_clocks(1)
        self.page.evaluate('placeCardInSlot(cardKey(prac.sequence[1]),0)')
        self.assertEqual(self.page.locator('.prac-result-item.correct').count(),1)
        self.assertEqual(self.page.evaluate('prac.placedCount'),1)

    def test_keyboard_cannot_place_after_deadline(self):
        self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2')
        self.body_focus();self.page.keyboard.press('ArrowRight')
        self.advance_clocks(2100);self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('prac.placedCount'),0)
        self.assertTrue(self.page.locator('#pracResults').is_visible())

    def test_drag_started_before_deadline_cannot_finish_after_it(self):
        self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2')
        self.page.wait_for_timeout(50)
        rank=self.page.locator('.pool-item').first.locator('.fan-rank').bounding_box()
        slot=self.page.locator('.slot').first.bounding_box()
        self.page.mouse.move(rank['x']+rank['width']/2,rank['y']+rank['height']/2)
        self.page.mouse.down();self.page.mouse.move(rank['x']+20,rank['y']-30,steps=4)
        self.assertIsNotNone(self.page.evaluate('dragState'))
        self.advance_clocks(2100)
        self.page.mouse.move(slot['x']+slot['width']/2,slot['y']+slot['height']/2)
        self.page.mouse.up()
        self.assertEqual(self.page.evaluate('prac.placedCount'),0)
        self.assertIsNone(self.page.evaluate('dragState'))
        self.assertTrue(self.page.locator('#pracResults').is_visible())

    def test_expired_deck_switch_keeps_completed_answers(self):
        self.controlled_clocks();self.practice(2,104)
        self.page.evaluate('skipToRecall();prac.recallLimitSec=2;placeCardInSlot(cardKey(prac.sequence[0]),0)')
        self.advance_clocks(2100);self.page.evaluate('switchDeckTab(1)')
        self.assertEqual(self.page.evaluate('prac.activeDeck'),0)
        self.assertEqual(self.page.locator('.prac-result-item.correct').count(),1)
        self.assertTrue(self.page.locator('#pracResults').is_visible())

    def test_hidden_clock_does_not_go_backwards(self):
        self.controlled_clocks();self.page.evaluate('setMemoPreset(0)');self.practice()
        self.advance_clocks(5000)
        self.page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});testHidden=true;document.dispatchEvent(new Event('visibilitychange'));wallNow-=3600000;activeNow+=5000;testHidden=false;document.dispatchEvent(new Event('visibilitychange'));skipToRecall()")
        self.assertEqual(self.page.evaluate('prac.memoElapsed'),10)

    def test_return_to_practice_finishes_expired_multideck_recall(self):
        self.controlled_clocks();self.practice(2,104)
        self.page.evaluate("skipToRecall();switchDeckTab(1);placeCardInSlot(cardKey(prac.sequence[52]),0);prac.recallLimitSec=2;switchTab('catalog')")
        self.advance_clocks(2100);self.page.evaluate("switchTab('practice')")
        self.assertTrue(self.page.locator('#pracResults').is_visible())
        self.assertFalse(self.page.locator('#poolDock').is_visible())
        self.assertEqual(self.page.locator('.prac-result-item.correct').count(),1)

    def test_repeated_enter_on_start_button_keeps_sequence(self):
        self.page.evaluate("switchTab('practice')")
        self.page.locator('button[onclick="startPractice()"]').focus()
        self.page.keyboard.down('Enter')
        before=self.page.evaluate('JSON.stringify(prac.sequence)')
        self.page.keyboard.down('Enter');self.page.keyboard.up('Enter')
        self.assertEqual(self.page.evaluate('JSON.stringify(prac.sequence)'),before)
        self.assertEqual(self.page.evaluate('prac.groupIndex'),0)

    def test_memo_navigation_checks_deadline(self):
        for operation in ['memoNextGroup()','memoPrevGroup()']:
            with self.subTest(operation=operation):
                self.controlled_clocks();self.practice();self.page.evaluate('prac.memoLimitSec=2')
                self.advance_clocks(2100);self.page.evaluate(operation)
                self.assertTrue(self.page.locator('#pracRecall').is_visible())
                self.assertEqual(self.page.evaluate('prac.memoElapsed'),2)

    def test_foreground_system_clock_changes_do_not_change_elapsed(self):
        for jump in [-3600000,3600000]:
            with self.subTest(jump=jump):
                self.controlled_clocks();self.page.evaluate('setMemoPreset(0)');self.practice()
                self.advance_clocks(60000)
                self.assertEqual(self.page.evaluate("practiceElapsed('memo')"),60)
                self.page.evaluate('jump=>wallNow+=jump',jump)
                self.assertEqual(self.page.evaluate("practiceElapsed('memo')"),60)
                self.advance_clocks(5000);self.page.evaluate('skipToRecall()')
                self.assertEqual(self.page.evaluate('prac.memoElapsed'),65)

    def test_page_return_checks_deadline_without_interval(self):
        for event in ['focus','pageshow','visibilitychange']:
            with self.subTest(event=event):
                self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();prac.recallLimitSec=2')
                self.advance_clocks(2100)
                self.page.evaluate('name=>(name==="visibilitychange"?document:window).dispatchEvent(new Event(name))',event)
                self.assertTrue(self.page.locator('#pracResults').is_visible())

    def test_old_actions_cannot_mutate_completed_or_reset_attempt(self):
        self.controlled_clocks();self.practice();self.page.evaluate('skipToRecall();placeCardInSlot(cardKey(prac.sequence[0]),0);finishRecall()')
        before=self.page.evaluate('JSON.stringify(prac.slots)')
        self.page.evaluate('onSlotInteract(0);placeCardInSlot(cardKey(prac.poolCards[2]),1)')
        self.assertEqual(self.page.evaluate('JSON.stringify(prac.slots)'),before)
        self.page.evaluate('resetPractice();onSlotInteract(0);placeCardInSlot(cardKey(prac.poolCards[3]),1)')
        self.assertEqual(self.page.evaluate('JSON.stringify(prac.slots)'),before)

    def test_repeated_enter_does_not_advance_or_restart_attempt(self):
        self.practice();self.body_focus()
        self.page.keyboard.down('Enter');group=self.page.evaluate('prac.groupIndex')
        self.page.keyboard.down('Enter');self.page.keyboard.up('Enter')
        self.assertEqual(self.page.evaluate('prac.groupIndex'),group)
        before=self.page.evaluate('JSON.stringify(prac.sequence)')
        self.page.evaluate('startPractice()')
        self.assertEqual(self.page.evaluate('JSON.stringify(prac.sequence)'),before)

    def test_practice_seeded_pool_conservation(self):
        for decks in [0,1,2,5]:
            with self.subTest(decks=decks):
                self.practice(decks,17);self.page.evaluate('skipToRecall()')
                failures=self.page.evaluate('''()=>{
                    let seed=711;const rand=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n};
                    const errors=[];
                    for(let step=0;step<300;step++){
                        if(prac.usePerDeck&&rand(4)===0) switchDeckTab(rand(prac.decks));
                        const slot=rand(prac.slots.length);
                        if(rand(3)===0){selectedKey=null;onSlotInteract(slot)}
                        else {const cards=prac.poolCards.filter(c=>prac.poolCounts[cardKey(c)]>0);if(cards.length)placeCardInSlot(cardKey(cards[rand(cards.length)]),slot)}
                        saveActiveDeck();
                        const states=prac.usePerDeck?prac.perDeck:[prac];
                        for(const st of states){
                            const filled=st.slots.filter(Boolean);
                            if(st.placedCount!==filled.length) errors.push([step,'placed count']);
                            for(const c of DATA){const k=cardKey(c);const n=st.poolCounts[k]+filled.filter(v=>cardKey(v)===k).length;if(n!==1)errors.push([step,k,n])}
                        }
                    }
                    return errors;
                }''')
                self.assertEqual(failures,[])

    def test_invalid_time_is_clamped(self):
        for minutes,seconds,expected in [('-1','-30',0),('999','999',3659),('','',0)]:
            with self.subTest(minutes=minutes,seconds=seconds):
                actual=self.page.evaluate('''([m,s])=>{document.getElementById('pracMemoMin').value=m;document.getElementById('pracMemoSec').value=s;onCustomMemoTime();return prac.memoLimitSec}''',[minutes,seconds])
                self.assertEqual(actual,expected)

    def test_menu_mobile_desktop_resize(self):
        self.page.locator('#menuCollapse').click();self.assertFalse(self.page.locator('#sidebar').is_visible())
        self.page.reload();self.assertFalse(self.page.locator('#sidebar').is_visible())
        self.page.locator('#menuToggle').click();self.assertTrue(self.page.locator('#sidebar').is_visible())
        self.page.set_viewport_size({'width':390,'height':844});self.page.wait_for_timeout(300)
        self.page.locator('#menuToggle').click();self.page.wait_for_timeout(300)
        self.assertTrue(self.page.locator('#sidebar').is_visible())
        self.page.keyboard.press('Escape');self.page.wait_for_timeout(300)
        self.assertFalse(self.page.locator('#sidebar').is_visible())
        self.page.locator('#menuToggle').click();self.page.wait_for_timeout(300)
        self.page.set_viewport_size({'width':1440,'height':1000});self.page.wait_for_timeout(300)
        self.assertFalse(self.page.evaluate("document.body.classList.contains('menu-open')"))
        self.assertFalse(self.page.evaluate("document.getElementById('sidebar').inert"))

    def test_storage_unavailable_and_invalid_preferences(self):
        context=self.browser.new_context()
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script("Storage.prototype.getItem=()=>{throw new Error('denied')};Storage.prototype.setItem=()=>{throw new Error('denied')}")
        page.goto(self.url);self.assertTrue(page.locator('#displayArea').inner_text().strip());self.assertEqual(errors,[]);context.close()
        self.page.evaluate("localStorage.setItem('assocPrefs.v1',JSON.stringify({fmt:'invalid',unit:'invalid',dir:'invalid'}))")
        self.page.reload();self.assertEqual(self.page.evaluate('({...assoc})'),{'fmt':'input','unit':'one','dir':'toAssoc'})

    def test_short_wrong_images_are_not_accepted(self):
        self.assertEqual(self.page.evaluate("DATA.filter(c=>matchImage(c,'а')||matchImage(c,'ко')).map(cardCode)"), [])

    def test_drag_cleanup_when_reset_or_deck_switched(self):
        self.page.evaluate("""window.gestureListeners=new Map();
            for(const target of [document,window]){
                const add=target.addEventListener.bind(target),remove=target.removeEventListener.bind(target);
                target.addEventListener=(type,fn,opts)=>{if(['onPointerMove','onPointerUp','onPointerCancel','onWindowBlur','onVisibilityChange'].includes(fn.name)){if(!gestureListeners.has(type))gestureListeners.set(type,new Set());gestureListeners.get(type).add(fn)};return add(type,fn,opts)};
                target.removeEventListener=(type,fn,opts)=>{gestureListeners.get(type)?.delete(fn);return remove(type,fn,opts)};
            }""")
        for operation in ['resetPractice()', 'switchDeckTab(1)', 'finishRecall()', "switchTab('catalog')"]:
            self.practice(2,104);self.page.evaluate('skipToRecall()');self.page.wait_for_timeout(50)
            el=self.page.locator('.pool-item').first
            r=el.locator('.fan-rank').bounding_box()
            self.page.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2)
            self.page.mouse.down();self.page.mouse.move(r['x']+20,r['y']-30,steps=4)
            self.assertIsNotNone(self.page.evaluate('dragState && dragState.key'))
            self.page.evaluate(operation)
            self.assertEqual(self.page.evaluate('[...gestureListeners.values()].reduce((n,s)=>n+s.size,0)'),0,self.page.evaluate('[...gestureListeners].map(([t,s])=>[t,[...s].map(fn=>fn.name)])'))
            self.page.mouse.up()
            self.assertIsNone(self.page.evaluate('dragState'))
            self.assertFalse(self.page.locator('#dragGhost').is_visible())

    def test_real_timers_finish_both_phases(self):
        self.page.evaluate("switchTab('practice');setMemoPreset(1);prac.recallLimitSec=1;startPractice()")
        self.page.locator('#pracRecall').wait_for(state='visible',timeout=5000)
        self.page.locator('#pracResults').wait_for(state='visible',timeout=5000)
        self.assertEqual(self.page.evaluate('[prac.memoElapsed,prac.recallElapsed]'),[1,1])

    def test_wrong_and_empty_recall_scores(self):
        self.practice(0,7);self.page.evaluate('skipToRecall()')
        self.page.evaluate("""()=>{const seq=prac.sequence;placeCardInSlot(cardKey(seq[0]),0);placeCardInSlot(cardKey(seq[2]),1);finishRecall()}""")
        self.assertEqual(self.page.locator('.prac-result-item.correct').count(),1)
        self.assertEqual(self.page.locator('.prac-result-item.wrong').count(),1)
        self.assertEqual(self.page.locator('.prac-result-item.empty').count(),5)
        self.assertIn('1 / 7 (14%)',self.page.locator('#pracStatsBox').inner_text())

    def test_pool_labels_mouse_after_resize_and_removal(self):
        for width in [1440,390]:
            self.page.set_viewport_size({'width':width,'height':844})
            self.practice();self.page.evaluate('skipToRecall()');self.page.wait_for_timeout(50)
            for count in [52,47,2,1]:
                self.page.evaluate("""count=>{while(document.querySelectorAll('.pool-item').length>count){const c=prac.poolCards.find(c=>prac.poolCounts[cardKey(c)]>0);placeCardInSlot(cardKey(c),nextEmptySlotIndex())}}""",count)
                self.page.wait_for_timeout(40)
                for i in range(count):
                    self.page.evaluate("""i=>{const L=getFanLayout();L.grid.scrollLeft=Math.max(0,L.startX+i*L.step-L.fanW/2)}""",i)
                    el=self.page.locator('.pool-item').nth(i);r=el.locator('.fan-rank').bounding_box()
                    x,y=r['x']+r['width']/2,r['y']+r['height']/2
                    self.page.mouse.move(x,y);self.page.wait_for_timeout(20)
                    self.assertEqual(self.page.evaluate('fanFocusIndex'),i)
                    self.page.mouse.click(x,y)
                    self.assertEqual(self.page.evaluate('selectedKey'),el.get_attribute('data-key'))
                    self.page.evaluate('clearPoolSelection()')

    def test_touch_scroll_tap_and_drag_to_slot(self):
        page=self.browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(self.url)
        page.evaluate("switchTab('practice');startPractice();skipToRecall()");page.wait_for_timeout(100)
        y=page.locator('#poolGrid').bounding_box()['y']+30
        cdp=page.context.new_cdp_session(page)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':320,'y':y}]})
        for x in [280,240,200,160,120,80]:
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y}]});page.wait_for_timeout(25)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(1200)
        self.assertGreater(page.evaluate('document.getElementById("poolGrid").scrollLeft'),100)
        self.assertIsNone(page.evaluate('dragState'))
        page.evaluate("document.getElementById('poolGrid').scrollLeft=0");page.wait_for_timeout(100)
        rank=page.locator('.pool-item').first.locator('.fan-rank').bounding_box()
        x,y=rank['x']+rank['width']/2,rank['y']+rank['height']/2
        page.touchscreen.tap(x,y);key=page.locator('.pool-item').first.get_attribute('data-key')
        self.assertEqual(page.evaluate('selectedKey'),key,page.evaluate('({scroll:document.getElementById("poolGrid").scrollLeft,focus:fanFocusIndex,drag:dragState&&dragState.key})'))
        page.evaluate('clearPoolSelection()')
        page.locator('.slot').first.scroll_into_view_if_needed();page.wait_for_timeout(80)
        page.evaluate("window.scrollBy(0,document.querySelector('.slot').getBoundingClientRect().y-80)");page.wait_for_timeout(80)
        target=page.locator('.slot').first.bounding_box();rank=page.locator('.pool-item').first.locator('.fan-rank').bounding_box()
        x,y=rank['x']+rank['width']/2,rank['y']+rank['height']/2
        tx,ty=target['x']+target['width']/2,target['y']+target['height']/2
        cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for f in [0.1,0.25,0.5,0.75,1]:
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+(tx-x)*f,'y':y+(ty-y)*f}]});page.wait_for_timeout(30)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        self.assertEqual(page.evaluate('cardKey(prac.slots[0])'),key)
        self.assertIsNone(page.evaluate('dragState'))
        self.assertEqual(errors,[]);page.close()

    def test_layout_does_not_overflow_at_common_sizes(self):
        for width,height in [(320,640),(390,844),(768,1024),(1024,768),(1920,1080)]:
            self.page.set_viewport_size({'width':width,'height':height})
            for name in ['assoc','catalog','practice']:
                self.page.evaluate('name=>switchTab(name)',name)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)
            self.practice();self.page.evaluate('skipToRecall();selectedKey=cardKey(prac.poolCards[13]);updatePoolSelectionUI()')
            card=self.page.locator('#poolPreviewCard').bounding_box();text=self.page.locator('.pool-preview-info').bounding_box()
            self.assertGreaterEqual(text['x']-card['x']-card['width'],15)
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)
            self.page.evaluate('resetPractice()')

    def test_landscape_dock_leaves_board_visible(self):
        self.page.set_viewport_size({'width':844,'height':390})
        self.practice();self.page.evaluate('skipToRecall();selectedKey=cardKey(prac.poolCards[0]);updatePoolSelectionUI()')
        self.assertLess(self.page.locator('#poolDock').bounding_box()['height'],390*0.75)

    def test_actions_do_not_accept_another_cards_phrase(self):
        incorrect=self.page.evaluate("""()=>DATA.flatMap(c=>DATA.filter(other=>cardCode(other)!==cardCode(c)&&matchAction(c,actionOf(other)[0])).map(other=>[cardCode(c),cardCode(other)]))""")
        self.assertEqual(incorrect,[])
        self.assertFalse(self.page.evaluate("matchAction(DATA[0],'покрывает')"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
