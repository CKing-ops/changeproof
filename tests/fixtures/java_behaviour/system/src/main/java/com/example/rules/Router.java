package com.example.rules;

import java.util.List;

/** Synthetic: needs a constructor argument, so the probe cannot build it. */
public class Router {
    private final String region;

    public Router(String region) {
        this.region = region;
    }

    public int route(List<String> hops) {
        return hops.size() + region.length();
    }
}
