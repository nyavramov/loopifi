# Profiling How-To

So you wanna profile `loops.py`? Check out this method.

## cProfile

```sh
$ python -m cProfile loops.py Samples/sample.mp4
```

## QCacheGrind

### Dependencies

```sh
$ brew install graphviz
$ brew install qcachegrind --with-graphviz
$ pip install pyprof2calltree
```

### Steps

```sh
$ python -m cProfile -o loops.cprof loops.py Samples/sample.mp4
$ pyprof2calltree -k -i loops.cprof
```

## Sources

- https://julien.danjou.info/guide-to-python-profiling-cprofile-concrete-case-carbonara/
- https://stackoverflow.com/questions/4473185/do-you-have-kcachegrind-like-profiling-tools-for-mac