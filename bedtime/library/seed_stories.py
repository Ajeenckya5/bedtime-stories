"""Ten hand-written stories that ship with the system.

They set the quality bar, give memory something to retrieve on day one, and act
as a regression net - tests/test_library_bias.py asserts all ten pass the gate.
Balance is deliberate: 4 girl protagonists, 3 boy, 1 sibling pair, 2
"""

from typing import Any, Dict, List

SEED_STORIES: List[Dict[str, Any]] = [
    {
        "id": "lib01",
        "title": "Amara and the Shallow End",
        "category": "everyday_courage",
        "protagonist": "girl",
        "characters": ["Amara", "Coach Dee"],
        "request": "a story about a girl who is nervous about her swimming lesson",
        "story": """Amara had a plan, and the plan was to be sick on Tuesday.

She practised her sick face in the bathroom mirror on Monday night. It did not look like a sick face. It looked like a face that had smelled something bad and was being polite about it. She tried again with a hand on her forehead, the way people did on television. That only made her look like she was checking whether her head was still there. She gave up and went to bed and hoped very hard instead.

Tuesday came anyway. Tuesdays always do.

The pool smelled sharp and blue, the way it always did. The sound of it bounced off the ceiling and came back twice as loud. Other children were already in the water, shrieking, which everyone said meant they were having fun. Amara was not convinced. She sat down on the cold tiled edge with her toes in the water and her hands squeezed into two tight knots on her knees.

Coach Dee came and sat down next to her. She did not say don't be scared. She did not say it's easy once you try. She put her own feet in the water and looked at the far wall for a while.

"That water's freezing," she said at last. "Isn't it."

"Yes," said Amara.

"Terrible." Coach Dee shook her head slowly. "Worst water in town. I've swum in a lot of pools. This one is the coldest and the bluest, and it smells the most. I don't know how anybody stands it."

Amara laughed. It was a small laugh and it came out of her by surprise. Afterwards there was a bit more room in her chest than there had been before. She put one foot in properly. Then the other one. The water came over her ankles and it really was freezing, which somehow made it easier. At least somebody had already said so.

"Right," said Coach Dee. "Now do nothing."

Amara looked up at her.

"Stand in the shallow end," said Coach Dee, "and be cross about how cold it is. That's the whole lesson. If anybody asks, tell them I said so."

So that is what she did. She stood in the shallow end with the water at her waist and she was extremely cross about it. She did not swim. She did not put her face in. Nobody made her. When the whistle went she climbed out and got dry and went home and ate two pieces of toast.

The next Tuesday she stood there again. The Tuesday after that she crouched down slowly until the water touched her chin, and she stayed like that for a long time, being cross. In the fourth week she blew bubbles. In the fifth she let her feet leave the bottom for as long as it takes to say a short word. Then she put them straight back down and looked around to see if anyone had noticed. Coach Dee was looking at the far wall again. She was smiling at it.

There was no whole length that term. There was not one the term after either. But by the summer she could float on her back with her ears under and the ceiling far away above her. The noise of everyone else went soft and round. She found she rather liked it there.

Her mum asked her once what had changed.

"Nothing," said Amara. "It's still the worst water in town."

Goodnight, Amara. Goodnight, Coach Dee, who knew what to say.

Goodnight, terrible freezing water.""",
    },
    {
        "id": "lib02",
        "title": "The Cat Who Chose Malik",
        "category": "animal_friendship",
        "protagonist": "boy",
        "characters": ["Malik", "Sock"],
        "request": "a story about a boy and a stray cat",
        "story": """The cat arrived on a Thursday and did not ask permission.

Malik found it sitting on the back step. It looked as though it had been sitting there for years and was surprised that anyone was making a fuss. It was grey and slightly dented on one ear. It looked at him for a long moment, decided something, and then looked away at a bird instead.

"You can't stay," he told it.

It stayed.

He was not allowed a cat. He knew this the way he knew the alphabet, all the way through and without stopping. His mum was not unkind about it. She was just tired, and cats cost money. There had already been a conversation about it in the spring that ended with everybody feeling a bit flat. So he did not ask again. He carried a saucer of water out to the step, put it down at a distance that seemed polite, and went back inside without looking round.

The next morning the saucer was empty and the cat was on the wall.

This went on. He would come out and sit on the step with a book. It would appear on the wall. The two of them would ignore each other with tremendous concentration. If he moved towards it, it left. If he sat very still and read out loud, it came a little closer and pretended to be interested in something else nearby. He learned this quickly and did not test it. Being still was not hard for him. He was good at it in the way some people are good at whistling.

One evening he sat with his back against the door and his book open on his knees, reading a page about volcanoes for the fourth time. Something warm leaned against his ankle.

He did not move. He did not look down. He read the whole page about volcanoes again in a completely normal voice, while a small grey weight settled against his leg and began, very quietly, to rumble.

They stayed like that until the light went orange and then blue.

When his mum came out to call him in she stopped in the doorway. She said nothing at all for a while. Then she said, "How long has that been going on."

"Two weeks," he said. "It comes for the water. It doesn't belong to anyone. I checked the whole street."

She looked at the cat. The cat, sensing an important moment, chose that instant to fall over sideways and go to sleep.

"It has one sock," she said.

It did have one sock. Three grey feet and one white one, like it had stepped in something and then given up on the idea.

Nobody ever said the cat could stay. What happened instead was quieter than that. A second saucer appeared by the step on Saturday. Then a folded towel turned up in the corner where the wall met the door. Then one evening his mum came home with a small bag of dry food and put it in the cupboard without mentioning it. Malik put it back in exactly the same place after using it, so that neither of them would have to say anything.

By the autumn it slept indoors. It chose the third stair, which was a strange choice, and it would not be moved off it. It still left when anybody rushed at it. It still came back when everybody was still.

He never did decide whether he had got a cat or the cat had got a boy.

Goodnight, Malik. Goodnight, third stair.

Goodnight, Sock, you difficult animal.""",
    },
    {
        "id": "lib03",
        "title": "Rosa, Theo and the Sixteen Screws",
        "category": "family_belonging",
        "protagonist": "girl and boy",
        "characters": ["Rosa", "Theo", "Mum"],
        "request": "a story about a brother and sister building something together",
        "story": """The shelf came in a flat box with a picture of a shelf on the front, which Rosa said was cheating.

Their mum tipped the box out onto the living room floor. Everything came with it. Six long pieces of wood, four short ones, a small paper bag of screws, and one folded sheet of instructions with no words on it at all. Only drawings of hands doing things. Theo picked up the sheet and turned it round twice.

"Is it upside down?"

"It's upside down whichever way you hold it," said their mum. "That's the style."

She was good at this sort of thing. She fitted radiators for a living and came home with her hands smelling faintly of metal. She could look at a thing for a moment and know which end of it was the beginning. But she sat back on her heels and handed the sheet to Rosa. "You two do it. I'll do the tea. Shout if it catches fire."

So they did it. Rosa was nine and read the drawings out loud in the voice of somebody reading a very serious document. Theo was six and was in charge of the screws. He had poured them into a saucer and arranged them by size, because he liked things in order, and nobody had asked him to do it.

It went well for about twenty minutes.

The trouble started with the long pieces. They were nearly the same as each other but not quite, and the difference mattered a great deal. The frame went together and stood up on its own, which was thrilling. Then it leaned slowly and thoughtfully to the left, like somebody remembering they had left the oven on.

"That's wrong," said Theo.

"I know it's wrong."

"It's very wrong."

"Theo."

They took it apart. They put it back together the other way and it leaned to the right instead, which was somehow worse. Rosa said a word she had heard at school and then looked quickly at the kitchen door. Theo said nothing at all, which was what he did when he was thinking. He began laying the pieces out on the carpet in a long row, shortest to longest.

"There," he said.

There were sixteen screws in the saucer. The paper bag had said twelve.

"Mum," Rosa called. "Are the extra screws meant to be there?"

"Nope," said their mum from the kitchen.

The two of them looked at each other. Then they looked at the row of wood on the carpet. Laid out end to end like that, it was extremely obviously two different lengths, and it had been the whole time.

It took another hour. Theo held things still while Rosa turned the screwdriver, because his hands were steadier and her arms were longer. Neither of them said this out loud; it simply became true. At one point the whole thing fell over onto the sofa. They laughed so much that their mum came to the door to see whether anybody needed help, and went away again when it was clear that nobody did.

At half past seven there was a shelf. It stood against the wall by the window and it did not lean in any direction whatsoever. Four screws were left over in the saucer, and Theo would not throw them away.

They put a plant on it. Then they took the plant off and put on the good bowl, the heavy one, to prove a point. It held.

"We should have started with the row," said Rosa.

"I know," said Theo. "You wouldn't listen."

Goodnight, Rosa. Goodnight, Theo.

Goodnight, wonky shelf that is not wonky. Goodnight, four extra screws.""",
    },
    {
        "id": "lib04",
        "title": "Why the Moon Followed Jun Home",
        "category": "curiosity_learning",
        "protagonist": "boy",
        "characters": ["Jun", "Dad"],
        "request": "why does the moon follow you when you walk?",
        "story": """Jun noticed the moon was following him somewhere between the shop and the corner.

He stopped walking. The moon stopped too. He took four steps and it came along without hurrying. He hid behind his dad's coat and looked out, and there it was, waiting above the roofs with an air of having been there the whole time.

"It's following me," he said.

"Is it," said his dad.

"It is. Watch." He ran ahead to the postbox and turned round with his arms out, as if catching somebody in the act. The moon had come too. It was over the postbox now instead of over the shop, which proved it.

His dad thought about this for the length of two lampposts. He was not a man who answered quickly. In the summer Jun had asked him why the sea was salty. He had said he would need to check. Three days later he brought it up again over breakfast with an actual answer, which Jun found very satisfying.

"Why do you think it's doing that?" he said.

"Because it likes me best."

"That's a good reason. Any others?"

Jun considered. "Because it's on a very long string."

"Also good." They walked a bit. "How long would the string have to be?"

This was harder than it looked. Jun tried to picture the string and found the problem straight away. It would have to go all the way up. It would have to be longer than the tallest crane in the world. Longer than the whole town. It would get tangled in the trees. Somebody would have noticed by now. He said all of this out loud and his dad agreed that it was a serious difficulty.

"Try this," said his dad. "Look at the postbox. Now walk."

Jun walked. The postbox slid backwards past his shoulder and was gone.

"Now the church tower."

The tower went too, but slower. It took nearly the whole street to leave.

"Now that hill, the far one behind the houses."

The hill hardly moved at all. It sat there while they walked half the road, drifting so slowly that he had to keep checking.

"So," said his dad. "Near things go past fast. Far things go past slow. What about something very, very far away?"

Jun stopped in the middle of the pavement.

"It wouldn't go past at all," he said.

"No."

"It would just... stay."

"It would just stay."

He looked up. The moon sat where it had been sitting all along, over the roofs, patient and enormous and extremely far away. It was not on a string. It was not following anybody. It was simply so distant that walking to the corner made no difference to it whatsoever, and that was somehow better than the string, and also much stranger.

"How far?" he said.

"Further than you can walk in your whole life. I'll find the number."

"You said that about the sea."

"I found the number about the sea."

"You did," Jun admitted.

They turned in at the gate. He looked back over his shoulder once from the doorstep, just to check. The moon was still there over the roofs. Going nowhere. Not following, and not on a string.

He decided he liked it better this way. A moon that followed one boy home was a small sort of moon. A moon that stayed still while the entire town walked underneath it was something else again.

Goodnight, Jun. Goodnight, hill that hardly moved.

Goodnight, extremely distant moon.""",
    },
    {
        "id": "lib05",
        "title": "Nadia and the Map With No X",
        "category": "adventure_quest",
        "protagonist": "girl",
        "characters": ["Nadia", "Grandpa Bo"],
        "request": "an adventure story about a girl who finds an old map",
        "story": """The map was in the drawer with the batteries that might still work.

Nadia was not looking for a map. She was looking for a rubber band, which is how most things are found. It was folded into eight and gone soft at the creases, and when she opened it out on the kitchen table it smelled faintly of pencil shavings.

There was a coastline. There were three hills with little humps drawn on them. There was a river that started nowhere and stopped in the middle of the paper. There was a wobbly square with a dot beside it. A line of dashes went off towards the edge.

There was no X.

She checked the back. She held it up to the window. She checked the corners in case somebody had put the X somewhere clever. Nothing.

"Grandpa Bo. Your map's broken."

He came and looked over her shoulder for a while, holding his tea. "Ah," he said. "That's mine. I was nine."

"Where's the treasure?"

"There isn't any."

Nadia put the map down and gave him a look that she had learned from her mother.

"It's not a treasure map," he said, sitting down. "It's a where-I-went map. That's the stream at the bottom of the field. Those are the three hills, except they're not really hills, they're one hill and two heaps. That square is the shed we weren't allowed in."

"What's the line of dashes?"

"That's how far I got before I had to be home for tea."

She looked at the dashes. They stopped quite suddenly, halfway to the edge of the paper. After them there was nothing at all. Just blank map, going on and on to the corner.

"What's past it?"

"No idea," said Grandpa Bo. "Never went. Then we moved."

That afternoon they took the map and walked out past the allotments. This took some doing. The paper was seventy years old, and the world had got on with things in the meantime. The stream was where it should be. The shed had become a fence. Two of the three hills were exactly where he had drawn them. The third turned out to be a heap after all, which he was very pleased about.

They found the end of the dashes at about four o'clock. It was not marked in any way. It was a bit of path beside a gate with a lot of nettles and one enormous flat stone, and it looked like nothing whatsoever.

"Here?" said Nadia.

"Here."

She stood on the flat stone and looked at the blank part, which was not blank at all in real life. It was a field, and then some trees, and then more field, and then the edge of everything.

"Can we go on?"

Grandpa Bo checked his watch, which was a joke, because there was no tea to be home for.

They went on for about twenty minutes. Then they sat down on the grass and drew it in. The field, the trees, a duck that was almost certainly a goose. She used her own pencil, on the blank part, in handwriting much worse than his nine-year-old handwriting.

The map now has two people's drawings on it. His stop halfway. Hers keep going, and they also stop, because it got dark and they were hungry.

"We'll do more," said Nadia.

"There's plenty of paper," he said.

Goodnight, Nadia. Goodnight, Grandpa Bo, who was nine once.

Goodnight, map of nothing in particular.""",
    },
    {
        "id": "lib06",
        "title": "Gus Only Knows One Ingredient",
        "category": "silly_humor",
        "protagonist": "animal",
        "characters": ["Gus", "the seals"],
        "request": "something very silly about a penguin who wants to be a chef",
        "story": """Gus the penguin had decided to become a chef, and Gus the penguin knew about one ingredient.

The ingredient was fish.

This was not, he felt, a serious problem. Plenty of great cooks had specialised. He put on an apron, which did not fit. He put on a tall white hat, which fell off. Then he wrote out a menu on a flat piece of ice, using a small stone.

The menu said: FISH.

Underneath, in smaller writing, it said: also fish.

The seals came because the seals came to everything. They arranged themselves in a heap and looked expectant, which for a seal mostly means looking damp.

"Starter," announced Gus. "Fish."

He served the fish. The seals ate the fish. It was, everyone agreed, a very good fish.

"Main course," said Gus, with a flourish that knocked his hat off again. "Fish — but sideways."

He had turned the fish round. That was the entire innovation. The seals ate it anyway and one of them clapped, or possibly just fell over.

"Dessert," said Gus.

There was a pause. A seal at the back stopped chewing.

"Fish," said Gus, "with a small hat on."

It was a very small hat. He had made it out of seaweed and it kept sliding off. He had to keep putting it back. By the time the plate reached the seals, the hat was mostly on the plate rather than the fish. Nobody minded. The seal at the back laughed so hard it slid off the heap entirely. Two other seals had to help it back up. Then the whole heap came apart. For a while there were just seals everywhere, laughing at a fish in a hat.

"Right," said Gus, when things had settled.

He looked at his menu. He looked at the sea, which was full of the only ingredient he had. Then he sat down on the ice next to the heap, which had rebuilt itself into a slightly different shape. He took off his apron. He ate some fish himself, plainly, with no hat on it at all.

"Same again tomorrow?" said a seal.

"Same again tomorrow," said Gus.

The sun went down slowly, the way it does at the bottom of the world. It took hours about it. Everything turned the colour of the inside of a shell. The heap of seals got quieter and lumpier. Somebody was snoring, and it was not clear who, and nobody was going to investigate.

Gus folded his apron. He put the small seaweed hat carefully on top of it, for tomorrow. Perhaps one day he would learn a second ingredient. That would be a good day. There would be a new menu with two whole words on it.

But that was tomorrow's problem. Tonight there was a full heap of warm seals. There was a flat piece of ice with FISH written on it. There was the water going dark and quiet all the way out.

One of the seals opened an eye. "That was a good dessert," it said.

"It was one fish," said Gus.

"It had a hat on."

Gus thought about that. It had had a hat on. Nobody else on this entire stretch of ice had ever put a hat on a fish, and that had to count for something, even if the something was small and made of seaweed.

He waddled over and got in among the heap, near the bottom, where it was warmest.

Goodnight, Gus. Goodnight, apron that does not fit.

Goodnight, seals. Goodnight, fish.""",
    },
    {
        "id": "lib07",
        "title": "The Teapot That Hums",
        "category": "magic_wonder",
        "protagonist": "girl",
        "characters": ["Elif", "the teapot"],
        "request": "a magical story about a teapot",
        "story": """The teapot on the top shelf was brown and ugly and it hummed when nobody was looking.

Elif noticed it in the week she was staying at her aunt's, which was a week with a lot of quiet in it. The hum was very low. It was the sort of sound you feel in your teeth before you hear it with your ears. It only happened when the kitchen was empty and the light was going.

She tested this carefully, because she was that sort of person. She stood in the doorway and it hummed. She walked in and it stopped. She went out and waited and it started again. She came in backwards, which she felt was clever, and it stopped anyway.

On the fourth evening she gave up being clever. She came in normally, pulled out a chair, sat down at the table with her back to the shelf, and did not look at it at all.

After a while, the humming started.

It was a small round sound with no tune to it. It went along underneath the noise of the fridge, rising a little and falling a little. It was the way somebody hums when their hands are busy and their mind is elsewhere. She sat very still and let it happen and did not turn round.

"You hum," she said eventually, to the table.

The humming carried on, which she took as agreement.

She came every evening after that. She would sit with her back to the shelf and do her puzzle book, or nothing at all. The teapot would hum. Outside the window the light went from orange to blue to properly dark. Sometimes the hum went slower when she was tired, which she was fairly sure was not her imagination.

On the last evening she asked her aunt about it.

"That old thing?" Her aunt looked up at the shelf. "It was my mother's. It doesn't pour. There's a crack all down the inside and the water comes out of the bottom before it comes out of the spout. I keep meaning to throw it away."

"Don't," said Elif.

Her aunt looked at her for a second. Then she said, "All right," and went back to the washing up. The matter was closed in the way things are closed in that house, without any fuss.

That night she came down for a glass of water. The kitchen was dark and the humming was going on quietly to itself. She stood in the doorway for a long time and let it.

She did not tell anybody at school. It was not the sort of thing that survives being told. On Sunday she put her bag in the car. Then she ran back in on the excuse of the toilet. She stood in the empty kitchen with her back to the shelf, and waited.

It hummed. She said, "Right then," and went.

She thinks about it more than she expected to. When the house is loud, or when there is too much of a day and not enough of her, she remembers the shelf. Somewhere up there is an ugly brown teapot that cannot pour. It is humming to itself in an empty kitchen, with the light going blue at the window.

It helps. She could not say exactly why.

Goodnight, Elif. Goodnight, aunt who said all right.

Goodnight, ugly brown teapot.""",
    },
    {
        "id": "lib08",
        "title": "The Lamp That Waited",
        "category": "bedtime_lullaby",
        "protagonist": "neutral",
        "characters": ["the lamp", "the moth", "the wind"],
        "request": "something very calm and sleepy",
        "story": """There is a lamp in the hall that gets left on.

Nobody decided this. It simply happens. Somebody goes up the stairs and does not turn it off, and then somebody else comes past later and does not turn it off either, and so it stays on. It has a yellow shade that has gone a bit brown at the top. The light it makes is small and round and does not reach the corners.

The house gets quiet in stages.

First the kettle stops ticking as it cools. Then the stairs finish creaking, one step at a time, going up. Then a tap runs somewhere above and stops. Then a door closes, softly, because everyone in this house closes doors softly at this time of night. Then there is only the fridge, humming to itself in the kitchen, which it will do all night and which nobody hears any more.

A moth comes to the lamp at about eleven.

It is a small brown moth and it is not very good at this. It bumps the shade. It sits down on the shade. It thinks about things for a while. Then it bumps the shade again, in case anything has changed, and it has not.

The moth stays. Moths do.

Outside, the wind is moving through the tree by the gate. It is not a big wind. It is the sort that lifts the smaller branches and puts them back down. It goes along the street and finds a gate that is not quite shut and moves it a little, and then it moves on and the gate goes quiet again.

The lamp does not mind waiting.

That is the thing about it. It has been on since half past seven and it will be on until somebody comes down for a glass of water. Then that person will notice it, and say "oh," and turn it off, and the hall will go dark and blue and stay that way until morning.

Nothing else is going to happen tonight.

The floorboard at the top of the stairs cools down and settles with one small tick. The moth gives up and goes and sits on the wall, higher up, where the warm air collects. The tree by the gate moves once more and then holds still. Somebody upstairs turns over and the bed makes a noise and then does not make any more.

The light stays on in the hall, small and yellow and steady.

It is not doing anything important. It is just there. It is enough light to find your way down if you needed to, and not enough to wake anybody, and that is exactly the right amount of light for a hall at this time of night.

Upstairs a small light goes off under a door. Then the last of the reading is over, and there is nothing but the sound of the house holding itself together in the ordinary way. Wood cooling. Water settling in a pipe. A car goes past outside and its light swings slowly across the ceiling and away.

The lamp waits.

It will wait a while yet. Somebody will come down eventually, in socks, holding the bannister, and they will not really be awake. They will fill a glass at the tap. On the way back up they will reach out without looking and click the switch, the way you do in your own house in the dark.

Then the hall will go blue.

The fridge hums. The moth sleeps on the wall. The wind has gone somewhere else.

Goodnight, lamp. Goodnight, brown shade.

Goodnight, moth. Goodnight, wind.

Sleep well.""",
    },
    {
        "id": "lib09",
        "title": "Kiran Goes Second",
        "category": "everyday_courage",
        "protagonist": "neutral",
        "characters": ["Kiran", "Priya", "Mr Adeyemi"],
        "request": "a story about a child who is scared to speak in front of the class",
        "story": """Everyone in the class had to say one thing about a place they liked, and Kiran was fourth.

This was the worst possible number. First would have been over quickly. Last would have been a long wait but at least the waiting would end. Fourth meant sitting through three other people while the middle of your body slowly turned into something that did not belong to you.

The list was on the board. Priya was first, then Tom, then Aisha, then Kiran.

Priya said she liked the swimming pool. She said it fast and sat down and did not seem to mind at all, which Kiran found impossible to understand. Tom talked about his nan's garden for slightly too long and had to be stopped. Aisha said "the library" and then nothing else, and Mr Adeyemi said that was a complete answer and thanked her.

Then it was Kiran.

The room turned round. That is what it felt like. All the faces came about like a gate swinging, and the words that had been ready and reasonable a minute ago went off somewhere and could not be found.

Nothing came out.

Mr Adeyemi did not fill the gap. He was good at this. He looked at his register, and then at the window, and let the room be quiet for a moment without making the quiet into a thing.

"Kiran," he said. "Do you want to go last instead?"

There was a small movement in the class, and it was not unkind. Somebody at the back said "yes please" about going last, and a few people laughed, and the faces turned away to look at the person who had spoken.

"Yes," said Kiran.

"Right. You're last. Zaid, you're fourth."

And that was all. Zaid went and talked about a chip shop. The list went on and the room stopped being about Kiran, and the middle of the body came back, slowly, over about six people.

By the time it got to the end, Kiran had said the words silently four times and they still worked.

"The allotment. My uncle's one. There's a tap that you have to hit."

It was eleven words. It took nine seconds. Then it was over, and the room did not fall down, and Mr Adeyemi said, "The hitting tap. Excellent," and moved on to the register.

Priya turned round on the way out. "Is it really a hitting tap?"

"You have to hit it in the right place," said Kiran. "There's a dent."

"Show me sometime."

Kiran said "all right," and it came out perfectly normally, in a corridor, to one person, which is a completely different thing from a room.

There will be a next time. There is always a next time with these. But there is also now a fact, and the fact is that once, at the end of a list, in a room with everybody in it, eleven words came out and nothing bad happened afterwards.

That is worth keeping. It goes in the drawer where you keep things like that.

Goodnight, Kiran. Goodnight, Mr Adeyemi, who let the quiet be.

Goodnight, tap with the dent.""",
    },
    {
        "id": "lib10",
        "title": "Ada Fixes the Wrong Thing",
        "category": "family_belonging",
        "protagonist": "girl",
        "characters": ["Ada", "Papa", "Dad"],
        "request": "a story about a girl who likes fixing things with her family",
        "story": """Ada could fix most things, which was the whole problem.

She had fixed the gate, and the drawer that stuck, and the lamp in the front room by wiggling the bit at the back until it stopped flickering. Papa said she had good hands. Dad said she had good hands and no patience, which was also true, and which Ada did not enjoy hearing.

The radio had been on the shelf in the kitchen for as long as she could remember. It was old and cream-coloured and heavy. It had two dials, and one of them did nothing at all. It made a noise like a wasp trapped in a jar whenever anybody tried to tune it.

"That's not broken," said Papa. "That's just how it is."

Ada disagreed. On Saturday, while the house was out, she got the small screwdriver and took the back off.

Inside it was beautiful. There were wires the colours of sweets and a row of things like little glass bottles, and a lot of dust, and a folded paper label gone brown at the edges. She took it all apart carefully and laid the pieces out on a tea towel in order, which is what Theo next door would have done, and which she was rather proud of.

Then she put it back together and it did not make any noise at all. Not even the wasp.

She sat and looked at it for a while.

The problem was not the fixing. She could probably fix it, given a week and the internet. The problem was that at four o'clock two people would come home and one of them would look at the shelf.

She got the pieces out again and worked until quarter to four. At quarter to four the radio was assembled, silent, and back on the shelf, and Ada was sitting at the kitchen table not doing anything.

Papa noticed before he had taken his coat off.

"You've had the back off."

"Yes."

"And?"

"It doesn't make the wasp any more." She looked at the table. "It doesn't make anything any more. I'm sorry. I thought I could do it."

Papa sat down. He did not say it's fine, and he did not say what were you thinking. He turned the radio round and looked at the four screws, which were back in, all four, and done up evenly.

"Did you keep the parts in order?"

"On a tea towel."

"Show me."

So she showed him, and he found the wire she had put back one hole along, which took about four minutes and involved him holding it up to the window and squinting. The wasp came back immediately. Everyone agreed this was a mixed result.

"It was my mother's," Papa said, putting it on the shelf. "It never worked properly. I don't want it to work properly. I want it to make that noise."

"That's not a very good reason."

"It's a terrible reason," he agreed. "Ask before the next one."

Dad came in then and was told the entire story twice, once by each of them, with different emphases.

Later Ada went and stood in front of the shelf on her own. The radio sat there being ugly and cream-coloured and making no noise, because nobody had turned it on, and she found she did not want to open it again.

She wanted to open the toaster instead. She decided she would ask first.

Goodnight, Ada. Goodnight, Papa. Goodnight, Dad.

Goodnight, wasp radio. Goodnight, excellent drawer.""",
    },
]


def by_category():
    out: Dict[str, List[str]] = {}
    for s in SEED_STORIES:
        out.setdefault(s["category"], []).append(s["id"])
    return out


def balance() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for s in SEED_STORIES:
        counts[s["protagonist"]] = counts.get(s["protagonist"], 0) + 1
    return counts
