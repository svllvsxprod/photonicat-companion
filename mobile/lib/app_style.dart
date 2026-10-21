import 'package:flutter/material.dart';

const yellow = Color(0xffffea00),
    muted = Color(0xffa0a197),
    rule = Color(0xff34362c);
TextStyle digits(
  double size, {
  Color color = yellow,
  FontWeight weight = FontWeight.w700,
}) => TextStyle(
  fontFamily: 'Orbitron',
  fontSize: size,
  color: color,
  fontWeight: weight,
);
