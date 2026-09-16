import re

path = "/home/eran1/vipassana/vipass.py"
src = open(path, encoding="utf-8").read()

# 1. corpus loading + grounding config, right after MANTRA block
anchor = 'WATCH_WINDOW = 8\nWATCH_UNIQ = 0.08\n'
assert anchor in src, "anchor not found"
addition = anchor + '''
# Rebbe Nachman grounding (2026-09-14, real text -- Likutei Moharan, public
# domain, fetched from Sefaria). Iddo asked for this specifically instead of
# generic self-babble: every GROUND_EVERY rounds, train GROUND_STEPS steps on
# a real random passage instead of only the mind's own output.
CORPUS_PATH = os.path.join(APP, "corpus.txt")
GROUND_EVERY = int(os.environ.get("VIPASS_GROUND_EVERY", "10"))
GROUND_STEPS = int(os.environ.get("VIPASS_GROUND_STEPS", "5"))
GROUND_BLOCK = 400   # chars of real text sampled per grounding step


def load_corpus():
    if not os.path.isfile(CORPUS_PATH):
        return ""
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return f.read()


def sample_passage(corpus, n):
    if len(corpus) <= n:
        return corpus
    import random
    start = random.randint(0, len(corpus) - n)
    return corpus[start:start + n]
'''
src = src.replace(anchor, addition)

# 2. vocab must include the corpus's real characters (Hebrew!) -- the old
# vocab only had SEED+MANTRA+English letters, so Hebrew text fed to it was
# 100% unknown-token noise.
old_vocab = '''    stoi, itos = build_vocab(
        SEED + MANTRA + "abcdefghijklmnopqrstuvwxyz .,"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ")'''
new_vocab = '''    corpus = load_corpus()
    stoi, itos = build_vocab(
        SEED + MANTRA + corpus + "abcdefghijklmnopqrstuvwxyz .,"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    print("corpus: %d chars loaded from %s" % (len(corpus), CORPUS_PATH),
          flush=True)'''
assert old_vocab in src, "vocab anchor not found"
src = src.replace(old_vocab, new_vocab)

# 3. wire grounding into the main loop -- every GROUND_EVERY rounds, train on
# a real passage BEFORE generating (so the generation itself reflects it),
# and record a "grounded" flag in history for the dash.
old_loop_body = '''        gen = generate(net, stoi, itos, thought, GEN_CHARS, TEMP)
        loss = train_on(net, opt, lossf, gen, stoi, TRAIN_STEPS)
        st = stats_of(gen)
        history.append({"r": rnd,
                        "loss": round(loss, 4) if loss else None,
                        "ent": st["entropy"], "uniq": st["unique_ratio"],
                        "fresh": fresh, "fed": fed})'''
new_loop_body = '''        grounded = False
        if corpus and GROUND_EVERY and rnd % GROUND_EVERY == 0:
            passage = sample_passage(corpus, GROUND_BLOCK)
            train_on(net, opt, lossf, passage, stoi, GROUND_STEPS)
            grounded = True
        gen = generate(net, stoi, itos, thought, GEN_CHARS, TEMP)
        loss = train_on(net, opt, lossf, gen, stoi, TRAIN_STEPS)
        st = stats_of(gen)
        history.append({"r": rnd,
                        "loss": round(loss, 4) if loss else None,
                        "ent": st["entropy"], "uniq": st["unique_ratio"],
                        "fresh": fresh, "fed": fed, "grounded": grounded})'''
assert old_loop_body in src, "loop anchor not found"
src = src.replace(old_loop_body, new_loop_body)

open(path, "w", encoding="utf-8").write(src)
print("patched OK")
