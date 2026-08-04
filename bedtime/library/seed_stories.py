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
        "story": """Amara had a plan. The plan was to be sick on Tuesday.

She practised her sick face in the mirror. It looked more like a face that had smelled something bad.

Tuesday came anyway. Tuesdays always do.

The pool smelled sharp and blue. Amara sat on the edge with her toes in the water and her hands squeezed tight.

Coach Dee sat down next to her. She did not say "don't be scared." She said, "That water's freezing, isn't it."

"Yes," said Amara.

"Terrible," said Coach Dee. "Worst water in town."

Amara laughed a small laugh. Then she put one foot in. Then the other.

"Now do nothing," said Coach Dee. "Just stand there and be cross about how cold it is."

So Amara stood in the shallow end and was cross about it. That was all she did for the whole lesson.

The next Tuesday she stood there again. The Tuesday after that, she crouched down until the water touched her chin.

She did not swim that day. She did not swim for three more weeks.

But on the fourth week she pushed off the wall and floated, just for a second, with her ears full of the strange underwater hum.

That night her hair still smelled of the pool. She lay in bed and listened to the hum inside her head.

Goodnight, Amara. Goodnight, terrible freezing water.""",
    },
    {
        "id": "lib02",
        "title": "The Cat Who Chose Malik",
        "category": "animal_friendship",
        "protagonist": "boy",
        "characters": ["Malik", "Sock"],
        "request": "a story about a boy and a stray cat",
        "story": """The cat was not a nice cat. Malik wanted that on the record.

It sat on the bins behind the flats and stared at people. One ear was folded over like a badly made bed. It had a white front paw, so Malik called it Sock, which it ignored.

Every day Malik put down a little food. Every day Sock waited until he walked away.

"He doesn't like you," said his brother.

"I know," said Malik.

He kept doing it anyway. It rained a lot that month.

One evening Malik put the food down and did not walk away. He sat on the step and looked at his shoes instead.

Sock ate. Malik did not move. His legs went stiff and prickly.

When he finally stood up, Sock stayed where he was.

That was all. Nothing else happened for eleven days.

On the twelfth day, Malik came out and Sock was already on the step. Waiting. Which is a completely different thing from being there.

Sock still did not want to be picked up. He made that extremely clear.

But when Malik sat down, the cat sat too, one step below, facing out at the car park like a small folded-eared guard.

They watched the rain start. Neither of them went in for a while.

Goodnight, Malik. Goodnight, Sock, you difficult animal.""",
    },
    {
        "id": "lib03",
        "title": "Rosa, Theo and the Sixteen Screws",
        "category": "family_belonging",
        "protagonist": "girl and boy",
        "characters": ["Rosa", "Theo", "Mum"],
        "request": "a story about a brother and sister building something together",
        "story": """The bookshelf came in a flat box with sixteen screws and a picture of a man smiling. Nobody in the family had ever smiled at a flat box.

"I'll do it," said Rosa.

"I'll do it," said Theo.

"You'll both do it," said Mum, "and I am going to sit here and watch, because I put in a whole radiator today and I am done."

Rosa read the instructions. Theo did not.

Theo had put three pieces together before Rosa finished page one. They were the wrong three pieces.

"Told you," said Rosa.

"Don't," said Mum, from the sofa, without opening her eyes.

They took it apart. Rosa read a step out loud, and Theo did it, and that turned out to be the only way it worked.

There were four screws left over at the end. Nobody could explain them.

They stood the bookshelf up. It leaned a little to the left, like it was listening to something.

"It's wonky," said Theo.

"It's ours," said Rosa.

They put the books on. The leaning got slightly worse. Mum opened one eye, looked at it, and decided to say nothing at all.

That night Theo could see the shelf from his bed, dark and lopsided against the wall, holding everything up exactly as well as it needed to.

Goodnight, wonky shelf. Goodnight, four extra screws.""",
    },
    {
        "id": "lib04",
        "title": "Why the Moon Followed Jun Home",
        "category": "curiosity_learning",
        "protagonist": "boy",
        "characters": ["Jun", "Dad"],
        "request": "why does the moon follow you when you walk?",
        "story": """Jun noticed it on the walk back from the shop. The moon was following him.

He stopped. The moon stopped.

He walked. It walked.

He did a small unnecessary run. It kept up easily, which was annoying.

"Dad," said Jun, "the moon is following me."

Dad thought about this the way he thought about everything, slowly, holding the bread.

"Try that lamp post," he said.

Jun watched the lamp post. It slid past him and vanished behind a hedge.

"Now the moon."

The moon did not slide past anything. It sat there, patient as a plate.

"The lamp post is close," said Dad. "So it swings by fast. The moon is so far away that walking doesn't get you any closer to it. Not even a bit. So it never slides."

"How far?"

"Very," said Dad. "You'd have to walk for years and years, and it still wouldn't move."

Jun tried to feel how far that was and could not.

At home he leaned on the window sill and checked. The moon was over the garages now, resting.

"Still there?" said Dad.

"Still there," said Jun.

He got into bed. The moon stayed at the window, not following him any more, just being enormously far away and shining anyway.

Goodnight, Jun. Goodnight, extremely distant moon.""",
    },
    {
        "id": "lib05",
        "title": "Nadia and the Map With No X",
        "category": "adventure_quest",
        "protagonist": "girl",
        "characters": ["Nadia", "Grandpa Bo"],
        "request": "an adventure story about a girl who finds an old map",
        "story": """The map was in a biscuit tin in the loft, under a broken torch and a photo of somebody's dog.

It was hand-drawn and soft at the folds. It showed the hill behind the houses, the stream, the bent tree. There was no X on it anywhere.

"What's it a map of?" Nadia asked.

Grandpa Bo squinted. "That's my map. I made it when I was nine."

"But there's no treasure."

"There wasn't any," he said. "I just liked the hill."

Nadia took the map out anyway. She had to. It was practically the law.

She found the bent tree, which was much bigger now and not very bent. She found the stream, which was in the wrong place, or possibly she was.

She got lost twice. Both times she found her way back by looking for the roofs.

At the top of the hill there was nothing at all. Just wind, and a view of the whole town looking small and busy and unaware of her.

She sat down. She could see her own house from here. Someone had left a window open.

She stayed until the streetlights came on in rows, one road at a time.

Then she walked home, folded the map along its soft old creases, and put it back in the tin for later.

Goodnight, hill. Goodnight, map of nothing in particular.""",
    },
    {
        "id": "lib06",
        "title": "Gus Only Knows One Ingredient",
        "category": "silly_humor",
        "protagonist": "animal",
        "characters": ["Gus", "the seals"],
        "request": "something very silly about a penguin who wants to be a chef",
        "story": """Gus the penguin opened a restaurant. The restaurant served fish.

Only fish. Fish soup, fish cake, fish on a small plate, and fish surprise, which was fish.

His first customer was a seal, who ate everything and said it was the best meal of his life.

His second customer was a seal. So was his third. So, in fact, were all of them, because seals were the only ones who came.

Gus decided the menu needed range.

He tried a salad. The salad was fish.

He tried a cake. Somehow, fish.

He tried something he called Surprise Tuesday. It was fish, and nobody was surprised, including Gus.

"I think," said Gus, "I might only know one ingredient."

"Yes," said the seals.

They said it kindly, all together, with their mouths full.

So Gus stopped worrying about range. He got a big piece of card and wrote one word on it, very large: FISH.

Underneath, in small letters, he wrote: it's good, though.

The seals came every night after that. They shuffled in and argued about the best table and ate far too much.

Gus cooked until his flippers ached and his little kitchen went quiet.

Then he turned the lights off. Outside, the sea did its slow shifting sound, and everybody slept.

Goodnight, Gus. Goodnight, seals. Goodnight, fish.""",
    },
    {
        "id": "lib07",
        "title": "The Teapot That Hums",
        "category": "magic_wonder",
        "protagonist": "girl",
        "characters": ["Elif", "the teapot"],
        "request": "a magical story about a teapot",
        "story": """The teapot came from a shop that sold everything and nothing useful.

It was brown and slightly ugly and had a chip on the lid.

It hummed.

Not always. Only when it was full, and only after the kitchen light was off, and only if you were not looking directly at it. Elif tested all three rules carefully, because rules about magic have to be tested.

The hum was low and a bit tuneless, like someone who does not know the words but likes the song.

Elif's grandmother said the teapot had always done that. She said it as though it were a fact about teapots in general.

"Does it hum for everyone?" Elif asked.

"It hums for whoever's in the kitchen at the wrong time of night," said her grandmother.

So Elif started being in the kitchen at the wrong time of night.

She never touched it. She just sat on the cold tiles in her socks with her back against the cupboard and listened.

Sometimes the hum went on for ages. Sometimes it stopped after a minute, for no reason Elif could work out.

She never did find out why it hummed. She asked, and it did not answer, because it was a teapot.

Some things are just true and stay true and do not explain themselves.

Elif went up to bed with the hum still going, softly, behind her.

Goodnight, ugly brown teapot.""",
    },
    {
        "id": "lib08",
        "title": "The Lamp That Waited",
        "category": "bedtime_lullaby",
        "protagonist": "neutral",
        "characters": ["the lamp", "the moth", "the wind"],
        "request": "something very calm and sleepy",
        "story": """In a small house at the top of a hill, there was a little lamp.

The lamp had one job. Every night, it waited for someone to come home.

At first the sky was blue. Then it went soft and pink. Then it went deep and quiet, like the inside of a shell.

The lamp glowed on.

A moth came to visit. "Are you tired?" asked the moth.

"A little," said the lamp. "But I like waiting. Waiting means someone is coming."

The wind came next, pushing at the window.

"Are you lonely?" asked the wind.

"Not tonight," said the lamp. "The house is full of sleeping things, and I am watching over all of them."

Then the door opened.

Small boots came in. A coat came off. A cup of milk was poured and carried carefully up the stairs.

"Goodnight, lamp," said a sleepy voice.

The lamp made its light smaller, and smaller, and smaller, until it was just a warm gold thread.

Outside, the moth found a leaf. The wind lay down in the grass.

And in the small house at the top of the hill, everyone was home.

Goodnight, lamp. Goodnight, moth. Goodnight, wind.

Sleep well.""",
    },
    {
        "id": "lib09",
        "title": "Kiran Goes Second",
        "category": "everyday_courage",
        "protagonist": "neutral",
        "characters": ["Kiran", "Priya", "Mr Adeyemi"],
        "request": "a story about a child who is scared to speak in front of the class",
        "story": """Everyone had to read one page out loud. Kiran was going ninth.

Kiran counted the readers. Eight, then seven, then six. The counting did not help.

Priya went fourth. She read too fast and got the whole thing over with in about nine seconds.

Kiran thought that was a very good idea and also completely impossible.

Mr Adeyemi came and crouched by the desk. His knees cracked. He pretended they hadn't.

"You can go last if you want," he said.

"That's worse."

"Yes," he agreed. "I thought it might be."

He waited.

"Can I go second?" said Kiran. "Tomorrow. Not today."

"Second tomorrow," said Mr Adeyemi, and he wrote it down, which somehow made it real.

Kiran did not read that day. Nobody said anything about it.

The next morning Kiran went second. The page was about tadpoles. Kiran's voice came out smaller than usual and slightly wobbly on the word *hatch*.

It took forty seconds. Then it was over, and the ordinary noise of the classroom came back, and Isla was already reading page three.

That was it. That was the whole thing.

Kiran thought about it again at bedtime, lying in the dark. Forty seconds. Wobbly on *hatch*.

Second tomorrow, if it comes up. Maybe.

Goodnight, Kiran. Goodnight, tadpoles.""",
    },
    {
        "id": "lib10",
        "title": "Ada Fixes the Wrong Thing",
        "category": "family_belonging",
        "protagonist": "girl",
        "characters": ["Ada", "Papa", "Dad"],
        "request": "a story about a girl who likes fixing things with her family",
        "story": """Ada could fix a bike, a zip, and one specific drawer that stuck.

She could not fix the kitchen radio, which had been making a noise like a wasp in a tin since March.

"Leave it," said Papa. "It's older than me."

Ada did not leave it. She took the back off at the kitchen table with the small screwdriver, the good one, the one that was technically Dad's.

Inside there was dust and wire and a small brown thing that looked burnt.

She poked the small brown thing. The radio made a noise like a much angrier wasp.

"Ada," said Dad, from his wheelchair by the door, not looking up from his crossword, "is that my screwdriver."

"No," said Ada.

"Mm," said Dad.

She worked on it for an hour and twenty minutes. She got dust on her nose. She learned three new words from Papa when the wasp noise got worse.

In the end she put it all back together and it was exactly as broken as before.

But the drawer that stuck did not stick any more, because she had done that too, on the way past, without really meaning to.

Nobody noticed until Tuesday. When they did, Papa opened and closed it about fifteen times, delighted.

The radio kept its wasp. Ada decided it could stay that way.

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
