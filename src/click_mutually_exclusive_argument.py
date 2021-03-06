from click import command, option, Option, UsageError


class MutuallyExclusiveOption(Option):
    def __init__(self, *args, **kwargs):
        self.mutually_exclusive = set(kwargs.pop('mutually_exclusive', []))
        help = kwargs.get('help', '')
        if self.mutually_exclusive:
            ex_str = ', '.join(self.mutually_exclusive)
            kwargs['help'] = help + (
                ' NOTE: This argument is mutually exclusive with '
                ' arguments: [' + ex_str + '].'
            )
        super(MutuallyExclusiveOption, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise UsageError(
                "Illegal usage: `{}` is mutually exclusive with "
                "arguments `{}`.".format(
                    self.name,
                    ', '.join(self.mutually_exclusive)
                )
            )

        return super(MutuallyExclusiveOption, self).handle_parse_result(
            ctx,
            opts,
            args
        )


@command(help="Run the command.")
@option('--jar-file', cls=MutuallyExclusiveOption,
        help="The jar file the topology lives in.",
        mutually_exclusive=["other_arg"])
@option('--other-arg',
        cls=MutuallyExclusiveOption,
        help="Another argument.",
        mutually_exclusive=["jar_file"])
def cli(jar_file, other_arg):
    print ("Running cli.")
    print ("jar-file: {}".format(jar_file))
    print ("other-arg: {}".format(other_arg))

if __name__ == '__main__':
    cli() # pylint: disable=no-value-for-parameter